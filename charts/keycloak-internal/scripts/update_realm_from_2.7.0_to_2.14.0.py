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


def update_client_config(access_token, keycloak_url):
    """Update the client configuration."""
    # Define the URL for the client
    client_id = "b7235af6-8c98-4d96-a1c3-94b94ed8d131"
    url = f"{keycloak_url}/admin/realms/CZERTAINLY/clients/{client_id}"

    # Define the payload for updating the client
    payload = {
        "clientId": "czertainly",
        "name": "czertainly",
        "redirectUris": ["/api/login/oauth2/code/internal"],
        "protocolMappers": [
            {
                "id": "debe702f-3d18-4eed-8909-806501f6afe2",
                "name": "Groups",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {
                    "aggregate.attrs": "false",
                    "userinfo.token.claim": "true",
                    "multivalued": "true",
                    "user.attribute": "groups",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "roles"
                }
            },
            {
                "id": "1ff9248b-c05e-48e8-b8db-0dc57e455620",
                "name": "Username",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-property-mapper",
                "consentRequired": False,
                "config": {
                    "introspection.token.claim": "true",
                    "userinfo.token.claim": "true",
                    "user.attribute": "username",
                    "id.token.claim": "true",
                    "lightweight.claim": "false",
                    "access.token.claim": "true",
                    "claim.name": "username",
                    "jsonType.label": "String",
                },
            },
            {
                "id": "a0cb4247-b04f-4ae1-beaf-761995705510",
                "name": "Audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.client.audience": "czertainly",
                    "introspection.token.claim": "true",
                    "userinfo.token.claim": "false",
                    "id.token.claim": "true",
                    "lightweight.claim": "false",
                    "access.token.claim": "true",
                },
            },
        ],
    }

    # Make the PUT request to update the client
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.put(url, headers=headers, json=payload, verify=verify_tls)
    response.raise_for_status()
    print(f"Client configuration updated successfully. Status code: {response.status_code}")


if __name__ == "__main__":
    # If used with --insecure switch script can ignore TLS certificates problems, use with caution
    parser = argparse.ArgumentParser(
        description="update_realm_from_2.7.0_to_2.14.0.py: script to upgrade realm CZERTAINLY in Keycloak for version 2.14.0")
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

        # Update the client configuration
        update_client_config(access_token, keycloak_url)
    except SSLError as e:
        print(f"An SSL error occurred, maybe try --insecure option? Exception: {e}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
