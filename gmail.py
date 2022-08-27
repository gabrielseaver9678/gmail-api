import base64

import copy

from email.message import EmailMessage
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import mimetypes

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build as build_api_client
from googleapiclient.http import HttpRequest

import os.path

from typing import List

TOKEN_JSON = "token.json"
CREDS_JSON = "credentials.json"
SCOPES = ["https://mail.google.com/"]

__gmail_service = None
def get_gmail_service ():
    global __gmail_service
    
    # Get the gmail service if we do not already have it
    if not __gmail_service:
        creds = None
        
        if os.path.exists(TOKEN_JSON):
            creds = Credentials.from_authorized_user_file(TOKEN_JSON, SCOPES)
        
        # Recreate credentials if there are no valid credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_JSON, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials
            with open(TOKEN_JSON, "w") as token:
                token.write(creds.to_json())
        
        __gmail_service = build_api_client("gmail", "v1", credentials=creds)
    
    # Return the gmail service
    return __gmail_service

class GmailMessage:
    def __init__ (self, subject:str="", body:str="", sender:str="", recipients:List[str]=[]):
        self.subject: str = subject
        self.body: str = body
        self.sender: str = sender
        self.recipients: List[str] = recipients
        self.__attachments = []
        
        self.__id: str = None # Not yet sent to or tracking a message on the gmail servers
        self.__thread_id: str = None
        self.__label_ids: List[str] = None
    
    def __get_email_message (self) -> EmailMessage:
        message = EmailMessage()
        message.set_content(self.body)
        message["To"] = ", ".join(self.recipients)
        message["From"] = self.sender
        message["Subject"] = self.subject
        
        for attachment in self.__attachments:
            with open(attachment[0], "rb") as file:
                attachment_data = file.read()
                message.add_attachment(attachment_data, attachment[1], attachment[2])
        
        return message
    
    def __get_encoded_message (self):
        message = self.__get_email_message()
        return base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    # TODO: Fix this
    def add_attachment (self, file:str):
        types, _ = mimetypes.guess_type(file)
        type, subtype = types.split("/")
        self.__attachments.append((file, type, subtype))
    
    def __from_response (self, response):
        self.__id = response["id"]
        if response["threadId"]:
            self.__thread_id = response["threadId"]
        if response["labelIds"]:
            self.__label_ids = response["labelIds"]
    
    def copy_message (self):
        message = copy.deepcopy(self)
        message.__id = None
        message.__thread_id = None
        message.__label_ids = None
        return message
    
    def message_is_tracking (self) -> bool:
        return self.__id != None
    
    def __check_uploaded_err (self):
        # Check that message isn't already uploaded (i.e. tracking an email already on gmail servers)
        if self.message_is_tracking():
            raise Exception("Cannot upload a message to gmail servers which is already uploaded")
    
    def import_message (self):
        self.__check_uploaded_err()
        
        service = get_gmail_service()
        raw_message = {"raw":self.__get_encoded_message()}
        response = service.users().messages().import_(userId="me", body=raw_message).execute()
        self.__from_response(response)
    
    def insert_message (self):
        self.__check_uploaded_err()
        
        service = get_gmail_service()
        raw_message = {"raw":self.__get_encoded_message()}
        response = service.users().messages().insert(userId="me", body=raw_message).execute()
        self.__from_response(response)
    
    # If trash is False, then the message will be instantly and permanently deleted
    # If trash is True, the message will be sent to the trash
    def delete (self, trash=True):
        if not self.message_is_tracking():
            raise Exception("Cannot trash or delete a message that isn't uploaded")
        
        service = get_gmail_service()
        if trash:
            pass
        else:
            service.users().messages().delete(userId="me", id=self.__id).execute()
    
    def send (self) -> HttpRequest:
        self.__check_uploaded_err()
        if self.sender != get_user_addr():
            raise Exception("Cannot send email from an adress which does not belong to you")
        
        service = get_gmail_service()
        raw_message = {"raw":self.__get_encoded_message()}
        response = service.users().messages().send(userId="me", body=raw_message).execute()
        self.__from_response(response)

def write_new_message (subject="", body="", recipients:List[str]=[]) -> GmailMessage:
    return GmailMessage(subject=subject, body=body, sender=get_user_addr(), recipients=recipients)

def get_user_addr () -> str:
    return get_gmail_service().users().getProfile(userId="me").execute()["emailAddress"]