import firebase_admin
from firebase_admin import credentials
from django.conf import settings
import os


def initialize_firebase():
    if not firebase_admin._apps:
        # credential_path = "aquanexis-7d862-firebase-adminsdk-fbsvc-b497c11d1f.json"

        # credential_path = os.environ.get("FIREBASE_CREDENTIAL_PATH")

        # if not credential_path:
        #     raise ValueError("FIREBASE_CREDENTIAL_PATH is not configured.")

        credential = credentials.Certificate("aquanexis-7d862-firebase-adminsdk-fbsvc-b497c11d1f.json")

        firebase_admin.initialize_app(credential)