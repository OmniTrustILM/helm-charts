#!/usr/bin/python3

# This script migrates a Keycloak realm from CZERTAINLY (pre-2.18.0 brand) to
# ILM (2.18.0+ brand). It must be run BEFORE `helm upgrade` to 2.18.0, while
# the previous-version Keycloak is still running and reachable.
#
# What it does (all idempotent — safe to run multiple times):
#   1. Renames realm "CZERTAINLY" -> "ILM" and sets loginTheme to "ilm".
#   2. Renames the auto-generated default role "default-roles-czertainly" -> "default-roles-ilm".
#   3. Renames the OAuth client used by the platform: clientId/name "czertainly" -> "ilm".
#   4. Updates the audience mapper on the renamed client: included.client.audience "czertainly" -> "ilm".
#   5. Updates baseUrl and redirectUris on the built-in `account` and `account-console` clients
#      to use the new realm path "/realms/ILM/account/".
#   6. Updates baseUrl and redirectUris on the built-in `security-admin-console` client
#      to use the new admin path "/admin/ILM/console/".
#
# After the script completes successfully, the Keycloak database matches the
# realm JSON shipped with chart 2.18.0 for every renamed identifier and URL,
# while preserving every UUID, user, session, group membership, and other
# realm state. The next Keycloak startup with `--import-realm` will see realm
# "ILM" already exists and skip the import without error.
#
# This script was tested on Keycloak 26.x.

import getpass
import argparse
import sys
import requests
from requests.exceptions import SSLError
import urllib3

verify_tls = True

OLD_REALM = "CZERTAINLY"
NEW_REALM = "ILM"
OLD_CLIENT_ID = "czertainly"
NEW_CLIENT_ID = "ilm"
OLD_DEFAULT_ROLE = "default-roles-czertainly"
NEW_DEFAULT_ROLE = "default-roles-ilm"
NEW_LOGIN_THEME = "ilm"


def authenticate(username, password, keycloak_url):
    """Authenticate and get an access token from Keycloak."""
    url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"
    payload = {
        "client_id": "admin-cli",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    response = requests.post(url, data=payload, verify=verify_tls)
    response.raise_for_status()
    return response.json()["access_token"]


def realm_exists(access_token, keycloak_url, realm_name):
    """Return True if a realm with the given name exists, False otherwise."""
    url = f"{keycloak_url}/admin/realms/{realm_name}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, verify=verify_tls)
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    response.raise_for_status()


def find_client_uuid(access_token, keycloak_url, realm, client_id):
    """Return the UUID of a client by its clientId attribute, or None if not found."""
    url = f"{keycloak_url}/admin/realms/{realm}/clients"
    params = {"clientId": client_id}
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, params=params, verify=verify_tls)
    response.raise_for_status()
    clients = response.json()
    if clients:
        return clients[0]["id"]
    return None


def rename_realm_and_set_login_theme(access_token, keycloak_url):
    """Rename CZERTAINLY -> ILM and set loginTheme to 'ilm' in a single PUT."""
    url = f"{keycloak_url}/admin/realms/{OLD_REALM}"
    payload = {"realm": NEW_REALM, "loginTheme": NEW_LOGIN_THEME}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.put(url, headers=headers, json=payload, verify=verify_tls)
    response.raise_for_status()
    print(f"Renamed realm '{OLD_REALM}' -> '{NEW_REALM}' and set loginTheme to '{NEW_LOGIN_THEME}'.")


def rename_default_role(access_token, keycloak_url):
    """Rename default-roles-czertainly -> default-roles-ilm in the ILM realm."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    # Probe old role first; if absent and new exists, treat as already done.
    # If neither exists (e.g., customized realm with the default role removed),
    # warn and continue rather than aborting the whole migration.
    old_url = f"{keycloak_url}/admin/realms/{NEW_REALM}/roles/{OLD_DEFAULT_ROLE}"
    response = requests.get(old_url, headers=headers, verify=verify_tls)
    if response.status_code == 404:
        new_url = f"{keycloak_url}/admin/realms/{NEW_REALM}/roles/{NEW_DEFAULT_ROLE}"
        check = requests.get(new_url, headers=headers, verify=verify_tls)
        if check.status_code == 200:
            print(f"Default role already named '{NEW_DEFAULT_ROLE}', skipping.")
            return
        if check.status_code == 404:
            print(
                f"WARNING: Neither '{OLD_DEFAULT_ROLE}' nor '{NEW_DEFAULT_ROLE}' role found. "
                "The realm appears to be customized; skipping default-role rename. "
                "If you have a custom default role, rename it manually after the migration completes."
            )
            return
        check.raise_for_status()
    response.raise_for_status()

    payload = {"name": NEW_DEFAULT_ROLE}
    response = requests.put(old_url, headers=headers, json=payload, verify=verify_tls)
    response.raise_for_status()
    print(f"Renamed default role '{OLD_DEFAULT_ROLE}' -> '{NEW_DEFAULT_ROLE}'.")


def rename_application_client(access_token, keycloak_url):
    """Rename the platform OAuth client: clientId/name 'czertainly' -> 'ilm'."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    uuid = find_client_uuid(access_token, keycloak_url, NEW_REALM, OLD_CLIENT_ID)
    if uuid is None:
        if find_client_uuid(access_token, keycloak_url, NEW_REALM, NEW_CLIENT_ID) is not None:
            print(f"Application client already renamed to '{NEW_CLIENT_ID}', skipping.")
            return
        print(f"WARNING: Could not find a client with clientId '{OLD_CLIENT_ID}' or '{NEW_CLIENT_ID}'. Skipping.")
        return

    url = f"{keycloak_url}/admin/realms/{NEW_REALM}/clients/{uuid}"
    response = requests.get(url, headers=headers, verify=verify_tls)
    response.raise_for_status()
    client = response.json()
    client["clientId"] = NEW_CLIENT_ID
    client["name"] = NEW_CLIENT_ID
    response = requests.put(url, headers=headers, json=client, verify=verify_tls)
    response.raise_for_status()
    print(f"Renamed application client clientId/name '{OLD_CLIENT_ID}' -> '{NEW_CLIENT_ID}'.")


def update_audience_mapper(access_token, keycloak_url):
    """On the ILM application client, update audience mappers from 'czertainly' to 'ilm'."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    uuid = find_client_uuid(access_token, keycloak_url, NEW_REALM, NEW_CLIENT_ID)
    if uuid is None:
        print(f"WARNING: Could not find client '{NEW_CLIENT_ID}' for audience-mapper update. Skipping.")
        return

    list_url = f"{keycloak_url}/admin/realms/{NEW_REALM}/clients/{uuid}/protocol-mappers/models"
    response = requests.get(list_url, headers=headers, verify=verify_tls)
    response.raise_for_status()
    mappers = response.json()

    updated = 0
    for mapper in mappers:
        config = mapper.get("config", {})
        if config.get("included.client.audience") == OLD_CLIENT_ID:
            config["included.client.audience"] = NEW_CLIENT_ID
            mapper_url = f"{list_url}/{mapper['id']}"
            response = requests.put(mapper_url, headers=headers, json=mapper, verify=verify_tls)
            response.raise_for_status()
            updated += 1

    if updated:
        print(f"Updated {updated} audience mapper(s) on client '{NEW_CLIENT_ID}'.")
    else:
        print(f"No audience mappers required updating on client '{NEW_CLIENT_ID}'.")


def update_client_realm_path_urls(access_token, keycloak_url, client_id, old_substr, new_substr):
    """Replace old_substr with new_substr in baseUrl and redirectUris of the given built-in client."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    uuid = find_client_uuid(access_token, keycloak_url, NEW_REALM, client_id)
    if uuid is None:
        print(f"WARNING: Could not find built-in client '{client_id}'. Skipping URL update.")
        return

    url = f"{keycloak_url}/admin/realms/{NEW_REALM}/clients/{uuid}"
    response = requests.get(url, headers=headers, verify=verify_tls)
    response.raise_for_status()
    client = response.json()

    base_url = client.get("baseUrl", "") or ""
    redirect_uris = client.get("redirectUris", []) or []
    new_base_url = base_url.replace(old_substr, new_substr)
    new_redirect_uris = [uri.replace(old_substr, new_substr) for uri in redirect_uris]

    if new_base_url == base_url and new_redirect_uris == redirect_uris:
        print(f"Client '{client_id}' URLs already migrated, skipping.")
        return

    client["baseUrl"] = new_base_url
    client["redirectUris"] = new_redirect_uris
    response = requests.put(url, headers=headers, json=client, verify=verify_tls)
    response.raise_for_status()
    print(f"Updated client '{client_id}' URLs: '{old_substr}' -> '{new_substr}'.")


def update_account_clients(access_token, keycloak_url):
    old_path = f"/realms/{OLD_REALM}/account/"
    new_path = f"/realms/{NEW_REALM}/account/"
    update_client_realm_path_urls(access_token, keycloak_url, "account", old_path, new_path)
    update_client_realm_path_urls(access_token, keycloak_url, "account-console", old_path, new_path)


def update_admin_console_client(access_token, keycloak_url):
    old_path = f"/admin/{OLD_REALM}/console/"
    new_path = f"/admin/{NEW_REALM}/console/"
    update_client_realm_path_urls(access_token, keycloak_url, "security-admin-console", old_path, new_path)


def run_post_rename_updates(access_token, keycloak_url):
    """Run all the operations that target the renamed (NEW_REALM) state."""
    rename_default_role(access_token, keycloak_url)
    rename_application_client(access_token, keycloak_url)
    update_audience_mapper(access_token, keycloak_url)
    update_account_clients(access_token, keycloak_url)
    update_admin_console_client(access_token, keycloak_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "update_realm_from_2.17.0_to_2.18.0.py: migrate a Keycloak realm from "
            "CZERTAINLY (pre-2.18.0 brand) to ILM (2.18.0+ brand). Renames the realm, "
            "the OAuth application client, the auto-generated default role, the "
            "audience mapper, and the built-in client URLs. Idempotent — safe to "
            "run multiple times."
        )
    )
    parser.add_argument(
        "--insecure", action="store_true", default=False,
        help="disable TLS certificate validation (default: %(default)s)",
    )
    args = parser.parse_args()

    if args.insecure:
        urllib3.disable_warnings()
        verify_tls = False

    keycloak_url = input("Enter the URL of the Keycloak (e.g., https://my.ilm.local/kc): ").rstrip("/")
    username = input("Enter the admin username: ")
    password = getpass.getpass("Enter the admin password: ")

    try:
        access_token = authenticate(username, password, keycloak_url)
        print("Authenticated successfully.")

        old_present = realm_exists(access_token, keycloak_url, OLD_REALM)
        new_present = realm_exists(access_token, keycloak_url, NEW_REALM)

        if old_present and new_present:
            print(
                f"ERROR: Both '{OLD_REALM}' and '{NEW_REALM}' realms exist. "
                "Refusing to migrate automatically — please consolidate manually."
            )
            sys.exit(1)

        if old_present:
            print(f"Found realm '{OLD_REALM}'. Migrating to '{NEW_REALM}'...")
            rename_realm_and_set_login_theme(access_token, keycloak_url)
            run_post_rename_updates(access_token, keycloak_url)
            print("Migration complete.")
        elif new_present:
            print(f"Realm '{NEW_REALM}' already exists. Verifying that all rebrand-related fields are migrated...")
            run_post_rename_updates(access_token, keycloak_url)
            print("Verification complete.")
        else:
            print(f"Neither '{OLD_REALM}' nor '{NEW_REALM}' realm found. Nothing to migrate.")
            sys.exit(0)

    except SSLError as e:
        print(f"An SSL error occurred, maybe try --insecure option? Exception: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
