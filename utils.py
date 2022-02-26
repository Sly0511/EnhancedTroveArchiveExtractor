import os
from hashlib import sha1
from json import dump, load

from aiofile import async_open
from tqdm import tqdm


class Progress(tqdm):
    def update_to(self, i, desc=None, total=None):
        if total is not None:
            self.total = total
        if desc is not None:
            self.desc = desc
        self.update(i)

def GetHash(path):
    data = open(path, "rb").read()
    return sha1(data).hexdigest()

async def AsyncGetHash(path):
    async with async_open(path, "rb") as File:
        data = await File.read()
        return sha1(data).hexdigest()

def FindTroveArchiveFolders(Path):
    if "extracted" not in Path.lower():
        for Thing in os.listdir(Path):
            PathThing = os.path.join(Path, Thing)
            if os.path.isdir(PathThing):
                for File in FindTroveArchiveFolders(PathThing):
                    yield File
            else:
                if Thing.endswith(".tfi"):
                    yield Path
                    continue

def FindTroveArchiveIndexes(Path):
    if "extracted" not in Path.lower():
        for Thing in os.listdir(Path):
            PathThing = os.path.join(Path, Thing)
            if os.path.isdir(PathThing):
                for File in FindTroveArchiveIndexes(PathThing):
                    yield File
            else:
                if Thing.endswith(".tfi"):
                    yield PathThing

def FindTroveArchiveFiles(Folder):
    for Thing in os.listdir(Folder):
        PathThing = os.path.join(Folder, Thing)
        if not os.path.isdir(PathThing):
            if PathThing.endswith(".tfa"):
                yield PathThing

def CreateDirectory(Path, Warn=False):
    if not os.path.exists(Path):
        os.makedirs(Path, exist_ok=True)
        if Warn:
            print(f"Created necessary directory:\n\t-> '{Path}'")

def LoadHashes(path):
    try:
        LoadedHashes = load(open(os.path.join(path, "EAEHashLog.json"), "r"))
    except:
        LoadedHashes = {}
    return LoadedHashes

def SaveHashes(path, hashes, filename="EAEHashLog.json"):
    CreateDirectory(path, True)
    dump(hashes, open(os.path.join(path, filename), "w+"))