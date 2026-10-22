"""Server-side storage. SQLite for local QA; Supabase for durable online tables."""
import hashlib
import copy
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import string
import time
import threading
import uuid
import requests
import engine


class Conflict(ValueError):
    pass


class StorageError(RuntimeError):
    pass


def digest(token):
    if not isinstance(token,str) or not 20<=len(token)<=256:
        raise engine.RuleError("Your player session is invalid. Reconnect using your saved recovery key.")
    return hashlib.sha256(token.encode()).hexdigest()


def room_code(value):
    value=str(value).strip().upper()
    if not re.fullmatch(r"[A-Z2-9]{6}",value):
        raise engine.RuleError("Enter a six-character room code.")
    return value


class SQLiteBackend:
    label="Local SQLite · one server"

    def __init__(self,path):
        self.path=str(path)
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS rooms(code TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS receipts(code TEXT, action TEXT, PRIMARY KEY(code,action))")

    def connection(self):
        return sqlite3.connect(self.path,timeout=15)

    def create(self,code,payload):
        try:
            with self.connection() as db:
                db.execute("INSERT INTO rooms VALUES(?,0,?)",(code,json.dumps(payload)))
            return True
        except sqlite3.IntegrityError:
            return False

    def read(self,code):
        with self.connection() as db:
            row=db.execute("SELECT version,payload FROM rooms WHERE code=?",(code,)).fetchone()
        if not row:
            raise engine.RuleError("Room not found. Check the code with your host.")
        return dict(version=row[0],payload=json.loads(row[1]))

    def commit(self,code,version,payload,action):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM receipts WHERE code=? AND action=?",(code,action)).fetchone():
                return "duplicate"
            cursor=db.execute("UPDATE rooms SET version=version+1,payload=? WHERE code=? AND version=?",(json.dumps(payload),code,version))
            if cursor.rowcount!=1:
                raise Conflict("The table changed. Review the latest state and try again.")
            db.execute("INSERT INTO receipts VALUES(?,?)",(code,action))
        return "ok"


class SupabaseBackend:
    label="Supabase · durable online tables"

    def __init__(self,url,key):
        if not url.startswith("https://"):
            raise StorageError("SUPABASE_URL must use HTTPS.")
        self.url=url.rstrip("/")+"/rest/v1/rpc/"
        self.headers={"apikey":key,"Content-Type":"application/json"}
        self._clients=threading.local()
        # Modern Supabase secret keys are not JWTs. Sending one as a Bearer
        # token makes PostgREST reject otherwise valid requests as Invalid JWT.
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"]="Bearer "+key

    def rpc(self,name,body):
        try:
            if not hasattr(self._clients,"session"):
                self._clients.session=requests.Session()
            response=self._clients.session.post(self.url+name,json=body,headers=self.headers,timeout=15)
        except requests.RequestException:
            raise StorageError("The shared database is temporarily unreachable. Your last saved turn is safe; try again.") from None
        if response.status_code>=400:
            # Never include server responses, headers, credentials, or connection strings in UI errors.
            raise StorageError("Database request failed. Check the Supabase migration and server secret configuration.")
        return response.json()

    def create(self,code,payload):
        return self.rpc("monopoly_create",dict(p_code=code,p_payload=payload))

    def read(self,code):
        result=self.rpc("monopoly_read",dict(p_code=code))
        if result is None:
            raise engine.RuleError("Room not found. Check the code with your host.")
        return result

    def commit(self,code,version,payload,action):
        result=self.rpc("monopoly_commit",dict(p_code=code,p_expected=version,p_payload=payload,p_action=action))
        if result=="conflict":
            raise Conflict("The table changed. Review the latest state and try again.")
        return result


class Service:
    def __init__(self,backend):
        self.backend=backend
        self._record=None
        self._code=None

    def create(self,name,token):
        session=secrets.token_urlsafe(32)
        pid=uuid.uuid4().hex
        payload=dict(state=engine.join(engine.new_game(),pid,name,token),members={digest(session):pid})
        for _ in range(10):
            code="".join(secrets.choice(string.ascii_uppercase+"23456789") for _ in range(6))
            if self.backend.create(code,payload):
                return dict(code=code,session=session,pid=pid)
        raise StorageError("Could not allocate a room code. Please retry.")

    def join(self,code,name,token):
        code=room_code(code)
        session=secrets.token_urlsafe(32)
        pid=uuid.uuid4().hex
        for _ in range(6):
            record=self.backend.read(code)
            payload=record["payload"]
            payload["state"]=engine.join(payload["state"],pid,name,token)
            payload["members"][digest(session)]=pid
            try:
                self.backend.commit(code,record["version"],payload,uuid.uuid4().hex)
                return dict(code=code,session=session,pid=pid)
            except Conflict:
                continue
        raise Conflict("Other players are joining. Try again.")

    def authenticate(self,record,session):
        pid=record["payload"]["members"].get(digest(session))
        if pid is None or pid not in record["payload"]["state"]["players"]:
            raise engine.RuleError("That recovery key does not belong to this room.")
        return pid

    def read(self,code,session):
        code=room_code(code)
        record=self.backend.read(code)
        pid=self.authenticate(record,session)
        advanced=engine.tick(record["payload"]["state"])
        if advanced!=record["payload"]["state"]:
            payload=copy.deepcopy(record["payload"])
            payload["state"]=advanced
            try:
                self.backend.commit(code,record["version"],payload,uuid.uuid4().hex)
            except Conflict:
                pass  # Another authenticated reader already advanced the clock.
            record=self.backend.read(code)
            pid=self.authenticate(record,session)
        self._code,self._record=code,record
        return record["payload"]["state"],record["version"],pid

    def act(self,code,session,version,action_id,action,**args):
        code=room_code(code)
        engine.require(isinstance(action_id,str) and re.fullmatch(r"[a-f0-9]{32}",action_id),"Invalid action identifier.")
        # Reuse this render's authenticated snapshot. The database still checks
        # its version atomically; a simultaneous action cannot overwrite it.
        record=copy.deepcopy(self._record) if self._code==code and self._record is not None else self.backend.read(code)
        pid=self.authenticate(record,session)
        if record["version"]!=version:
            raise Conflict("The table changed. Review the latest state and try again.")
        record["payload"]["state"]=engine.apply(record["payload"]["state"],pid,action,**args)
        result=self.backend.commit(code,version,record["payload"],action_id)
        # Only an acknowledged new commit can supply an immediate UI response.
        # Duplicate receipts must fetch the actual state instead of guessing it.
        self._record=dict(version=version+1,payload=record["payload"]) if result=="ok" else None
        self._code=code
        return result

    def committed_view(self,session):
        """Authenticated result for this action; subsequent polls still read storage."""
        if self._record is None:
            return None
        pid=self.authenticate(self._record,session)
        return copy.deepcopy(self._record["payload"]["state"]),self._record["version"],pid


@lru_cache(maxsize=4)
def cloud_backend(url,key):
    return SupabaseBackend(url,key)


def configured_backend(settings):
    url=os.environ.get("SUPABASE_URL") or settings.get("SUPABASE_URL")
    key=(os.environ.get("SUPABASE_SECRET_KEY") or settings.get("SUPABASE_SECRET_KEY")
         or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or settings.get("SUPABASE_SERVICE_ROLE_KEY"))
    if url and key:
        return cloud_backend(url,key)
    if os.environ.get("MONOPOLY_LOCAL")=="1" or settings.get("LOCAL_MODE",False):
        return SQLiteBackend(os.environ.get("MONOPOLY_DB","local-games.db"))
    return None
