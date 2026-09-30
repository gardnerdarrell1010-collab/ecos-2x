"""Owner-run Google installed-app reauthorization; no secrets in console output.

Reuses the existing client and exact existing scope. Preserves the legacy file.
The browser flow requires the owner. No Gmail messages are read or changed.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src'), str(ROOT/'scripts')]


def main():
    from resident2x_acceptance import secure_directory
    legacy = Path('D:/ECOS/Credentials/ecos-resident-ada-gmail-oauth.json')
    client_file = Path('D:/ECOS/Credentials/ecos-resident-ada-gmail-oauth-client.json')
    old = json.loads(legacy.read_text(encoding='utf-8-sig'))
    client = json.loads(client_file.read_text(encoding='utf-8-sig'))['installed']
    scopes = old['scopes']
    if isinstance(scopes, str): scopes = scopes.split()
    if scopes != ['https://www.googleapis.com/auth/gmail.modify']:
        raise ValueError('existing_scope_requires_review')
    if client['client_id'] != old['client_id']:
        raise ValueError('existing_client_mismatch')
    directory = ROOT/'.local/gmail-enrollment'
    if not directory.exists(): secure_directory(directory)
    destination = directory/'oauth.json'
    expected_account = json.loads((directory/'account.json').read_text())['account_scope']
    if destination.exists(): raise ValueError('existing_2x_credential_requires_reconciliation')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if query.get('state') != [state]:
                self.send_error(400, 'Invalid authorization state'); return
            if query.get('error') or not query.get('code'):
                result['error'] = True
            else: result['code'] = query['code'][0]
            self.send_response(200); self.send_header('Content-Type','text/plain');self.end_headers()
            self.wfile.write(b'Authorization response received. Return to PowerShell. No email was sent.')

    server = HTTPServer(('127.0.0.1', 0), Callback)
    server.timeout = 300
    redirect = 'http://localhost:'+str(server.server_port)+'/'
    auth_uri = client['auth_uri']; token_uri = client['token_uri']
    if urllib.parse.urlsplit(auth_uri).hostname != 'accounts.google.com' or token_uri != 'https://oauth2.googleapis.com/token':
        raise ValueError('unexpected_oauth_destination')
    url = auth_uri+'?'+urllib.parse.urlencode({'client_id':client['client_id'],'redirect_uri':redirect,
        'response_type':'code','scope':' '.join(scopes),'state':state,'access_type':'offline',
        'prompt':'consent','code_challenge':challenge,'code_challenge_method':'S256'})
    print('Approve the existing Gmail account in the browser. No credential transcription is required.', flush=True)
    try:
        if not webbrowser.open(url): raise ValueError('browser_open_failed')
        deadline = time.monotonic()+300
        while not result and time.monotonic()<deadline:
            server.timeout=max(1,deadline-time.monotonic())
            server.handle_request()
        if 'code' not in result: raise ValueError('authorization_not_completed')
        body=urllib.parse.urlencode({'client_id':client['client_id'],'client_secret':client['client_secret'],
            'code':result['code'],'code_verifier':verifier,'redirect_uri':redirect,'grant_type':'authorization_code'}).encode()
        with urllib.request.urlopen(urllib.request.Request(token_uri,data=body),timeout=30) as response:
            tokens=json.load(response)
        if not tokens.get('refresh_token'): raise ValueError('refresh_token_not_returned')
        # Verify Gmail scope and mailbox before preserving the refreshed credential.
        request=urllib.request.Request('https://gmail.googleapis.com/gmail/v1/users/me/profile',
                                       headers={'Authorization':'Bearer '+tokens['access_token']})
        with urllib.request.urlopen(request,timeout=30) as response: profile=json.load(response)
        if profile.get('emailAddress','').casefold() != expected_account.casefold():
            raise ValueError('mailbox_identity_mismatch')
        if tokens.get('scope') and set(tokens['scope'].split()) != set(scopes):
            raise ValueError('returned_scope_mismatch')
        payload={'client_id':client['client_id'],'client_secret':client['client_secret'],
                 'refresh_token':tokens['refresh_token'],'token_uri':token_uri,'scopes':scopes,
                 'account_scope':profile['emailAddress']}
        with destination.open('x',encoding='utf-8') as output: json.dump(payload,output)
        print('========== PASTE BACK ONLY THIS SECTION ==========')
        print('GmailReauthorization=PASS\nExistingClientReused=YES\nScopeExpanded=NO\nLegacyCredentialPreserved=YES\nMailboxReadback=PASS\nCredentialValuesPrinted=NO')
        print('========== END SECTION ==========')
    finally: server.server_close()


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        # Never print provider exception bodies, URLs, authorization codes or tokens.
        print('GmailReauthorization=FAILED; ErrorClass='+type(exc).__name__)
        raise SystemExit(1)
