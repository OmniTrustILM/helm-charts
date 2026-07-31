#!/usr/bin/python3

# This script was tested on Keycloak 24.0.2-0
import getpass
import argparse
import requests
from requests.exceptions import SSLError
import urllib3

verify_tls = True

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


def update_realm_login_theme(access_token, keycloak_url):
    """Update the login theme of the CZERTAINLY realm from 'czertainly' to 'ilm'."""
    url = f"{keycloak_url}/admin/realms/CZERTAINLY"

    payload = {
        "loginTheme": "ilm",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.put(url, headers=headers, json=payload, verify=verify_tls)
    response.raise_for_status()
    print(f"Realm login theme updated successfully to 'ilm'. Status code: {response.status_code}")


if __name__ == "__main__":
    # If used with --insecure switch script can ignore TLS certificates problems, use with caution
    parser = argparse.ArgumentParser(
        description="update_realm_from_2.14.0_to_2.17.0.py: script to upgrade realm CZERTAINLY in Keycloak for version 2.17.0")
    parser.add_argument('--insecure', action='store_true', default=False,
                        help='disable certificate validation (default: %(default)s)')
    args = parser.parse_args()

    if args.insecure:
        urllib3.disable_warnings()
        verify_tls = False

    # Get the base URL of Keycloak
    keycloak_url = input("Enter the URL of the Keycloak (e.g., https://my.czertainly.com/kc): ").rstrip("/")

    # Get the admin username and password securely
    username = input("Enter the admin username: ")
    password = getpass.getpass("Enter the admin password: ")

    try:
        # Authenticate the user
        access_token = authenticate(username, password, keycloak_url)
        print("Authenticated successfully!")

        # Update the realm login theme
        update_realm_login_theme(access_token, keycloak_url)
    except SSLError as e:
        print(f"An SSL error occurred, maybe try --insecure option? Exception: {e}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
