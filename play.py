import site
import docker
from problem_constants.constants import GCP_PROJECT

print(site.USER_BASE)


def main():
    cli = docker.from_env()
    cli.images.push('gcr.io/silken-impulse-217423/problem-worker-test')


def list_keys():
    # Imports the Google APIs client library
    from google.cloud import kms_v1

    # Your Google Cloud Platform project ID
    project_id = GCP_PROJECT

    # Lists keys in the "global" location.
    location = 'global'

    # Creates an API client for the KMS API.
    client = kms_v1.KeyManagementServiceClient()

    # The resource name of the location associated with the key rings.
    parent = client.location_path(project_id, location)

    # Lists key rings
    response = client.list_key_rings(parent)
    response_list = list(response)

    if len(response_list) > 0:
        print('Key rings:')
        for key_ring in response_list:
            print(key_ring.name)
    else:
        print('No key rings found.')


def encrypt_symmetric(plaintext, project_id='silken-impulse-217423',
                      location_id='global',
                      key_ring_id='deepdrive', crypto_key_id='deepdrive'):
    """Encrypts input plaintext data using the provided symmetric CryptoKey."""

    from google.cloud import kms_v1

    # Creates an API client for the KMS API.
    client = kms_v1.KeyManagementServiceClient()

    # The resource name of the CryptoKey.
    name = client.crypto_key_path_path(project_id, location_id, key_ring_id,
                                       crypto_key_id)

    # Use the KMS API to encrypt the data.
    response = client.encrypt(name, plaintext.encode())
    print(response.ciphertext)
    return response.ciphertext


def decrypt_symmetric(ciphertext, project_id='silken-impulse-217423',
                      location_id='global',
                      key_ring_id='deepdrive', crypto_key_id='deepdrive'):
    """Decrypts input ciphertext using the provided symmetric CryptoKey."""

    from google.cloud import kms_v1

    # Creates an API client for the KMS API.
    client = kms_v1.KeyManagementServiceClient()

    # The resource name of the CryptoKey.
    name = client.crypto_key_path_path(project_id, location_id, key_ring_id,
                                       crypto_key_id)
    # Use the KMS API to decrypt the data.
    response = client.decrypt(name, ciphertext)
    ret = response.plaintext.decode()
    return ret


if __name__ == '__main__':
    assert decrypt_symmetric(encrypt_symmetric(plaintext='hullo')) == 'hullo'
