import os
import subprocess
import sys
from asyncio import create_task, run, sleep
from datetime import datetime
from shutil import copy

from psutil import Process

from utils import *

# Intro Text
print(
"""
Welcome to Enhanced Trove Archive Extractor

- This tool extracts all game files it finds in current working directory
- The more files and folders you have the slower this process becomes
- The program will by default ignore all directories with ´extracted´ in their name
- This tool will create a file called `EAEHashLog.json` to store file states and avoid re extracting unchanged files (speeds up extractions of updates)
"""
)

# Process Management
CurrentProcess = Process()
StartedProcesses = []
# Directory setup
TroveDirectory = os.path.dirname(sys.executable)
TroveEXE = os.path.join(TroveDirectory, "Trove.exe")
#Manifest = os.path.join(TroveDirectory, "manifest.txt")
ExtractedDirectory = os.path.join(TroveDirectory, "Extracted")
ChangedDirectory = os.path.join(TroveDirectory, "Changed")
PreviewDirectory = os.path.join(TroveDirectory, "Catalog")
# Load previous logged hashes and create a backup for user cancellation
HashCache = LoadHashes(TroveDirectory)
HashCacheBackup = LoadHashes(TroveDirectory)
# Index all folders with index files
print("\nIndexing archives...")
ArchiveFolders = list(FindTroveArchiveFolders(TroveDirectory))
print(f"Found {len(ArchiveFolders)} Archive indexes.")
# This is a cache to avoid checking for changes on all directories
ExtractedArchivePaths = []

def SanityCheck():
    """Make sure Trove.exe is in directory and setup Hash File Log"""
    if not os.path.isfile(TroveEXE):
        print("\"Trove.exe\" was not found. Please run this executable in a Trove Game Directory.")
        return False
    # if not os.path.isfile(Manifest):
    #     print("\"manifest.txt\" was not found. Make sure Trove is properly installed.")
    #     return False
    if HashCache.get("Archives") is None:
        HashCache["Archives"] = {}
    if HashCache.get("Files") is None:
        HashCache["Files"] = {}
    SaveHashes(TroveDirectory, HashCache)
    return True

# Helper
def PrepareDirectory(Changes=False, Previews=False):
    """Ensure necessary folders are created"""
    if not os.path.isdir(ExtractedDirectory):
        CreateDirectory(ExtractedDirectory, True)
    if not os.path.isdir(ChangedDirectory) and Changes:
        CreateDirectory(ChangedDirectory, True)
    if not os.path.isdir(PreviewDirectory) and Previews:
        CreateDirectory(PreviewDirectory, True)

def GetTroveProcesses():
    """Get all subprocesses that were created by this script"""
    Children = CurrentProcess.children(recursive=True)
    for Child in Children:
        if Child.pid in StartedProcesses:
            yield Child.pid

def GetExtractedFiles(Directory):
    """A generator that outputs all files in a diretory"""
    for Thing in os.listdir(Directory):
        PathThing = os.path.join(Directory, Thing)
        if os.path.isdir(PathThing):
            for File in GetExtractedFiles(PathThing):
                yield File
        else:
            yield PathThing

def CutDirectory(Path, CutPath):
    """This allows me to keep trove's file structure"""
    return Path.replace(CutPath+"\\", "")

# Changes
async def SetHashFile(File, Progress):
    """Helps with first file hash log"""
    FilePathName = CutDirectory(File, ExtractedDirectory)
    if HashCache["Files"].get(FilePathName) is None:
        while True:
            try:
                HashCache["Files"][FilePathName] = await AsyncGetHash(File)
                break
            except OSError:
                ...
            except FileNotFoundError:
                break
    FileName = os.path.basename(FilePathName)
    Progress.update_to(1, desc=f"{FileName:<64}")

async def GetExtractedFileHashes():
    """Generate first file hash log"""
    if HashCache.get("Files"):
        return
    print("Running first time extracted folder hashing\nThis means you won't get listed changes this time.")
    print("Indexing extracted files...")
    ExtractedFiles = list(GetExtractedFiles(ExtractedDirectory))
    if not len(ExtractedFiles):
        print("No extracted files were found, change hash logging skipped.")
        return
    with Progress(total=len(ExtractedFiles)) as HashSaving:
        for i, File in enumerate(ExtractedFiles):
            create_task(SetHashFile(File, HashSaving))
            if i and not i%2000:
                await sleep(0.5)
        while HashSaving.n != len(ExtractedFiles):
            await sleep(10)
    SaveHashes(TroveDirectory, HashCache)
    print("Extracted files hashes were read.")

def CatalogBlueprint(File):
    """Open a Trove.exe subprocess to create blueprint previews"""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    subprocess.run(f'{TroveEXE} -tool catalog -dimension 256 -filter \"{File}\"', startupinfo=startupinfo)

def CheckExtractedFileHashes(Catalog=False):
    """Check new file hashes against stored ones"""
    ChangesDirectory = os.path.join(ChangedDirectory, datetime.now().strftime("%Y-%m-%d_%H.%M"))
    CreateDirectory(ChangesDirectory, True)
    print("Indexing extracted files...")
    ExtractedFiles = list(GetExtractedFiles(ExtractedDirectory))
    with Progress(total=len(ExtractedFiles)) as HashChecking:
        for File in ExtractedFiles:
            FileHash = GetHash(File)
            FileLocation = CutDirectory(File, ExtractedDirectory)
            FileName = os.path.basename(FileLocation)
            FilePath = os.path.dirname(FileLocation)
            if not ExtractedArchivePaths or FilePath in ExtractedArchivePaths:
                if (OldHash := HashCache["Files"].get(FileLocation)) is None or FileHash != OldHash:
                    HashCache["Files"][FileLocation] = FileHash
                    CreateDirectory(os.path.join(ChangesDirectory, FilePath))
                    NewFile = os.path.join(ChangesDirectory, FileLocation)
                    copy(File, NewFile)
                    if Catalog and FileName.endswith(".blueprint"):
                        CatalogBlueprint(FileName)
            HashChecking.update_to(1, desc=f"{FileName:<64}")
        SaveHashes(TroveDirectory, HashCache)
    print(f"Changes logged into \"{ChangesDirectory}\"")

# Extraction
def ExtractArchive(Archive, Output):
    """Open a Trove.exe subprocess to extract archives"""
    CMDProcess = subprocess.Popen(f'{TroveEXE} -tool extractarchive \"{Archive}\" \"{Output}\"')
    StartedProcesses.append(CMDProcess.pid)

async def ExtractArchiveFolder(ArchiveFolder):
    """This extracts all archives in a folder with an Index if any were changed"""
    Extracted = False
    for Archive in FindTroveArchiveFiles(ArchiveFolder):
        # Reduce size of Hash Database by cutting down key names
        ArchivePath = CutDirectory(Archive, TroveDirectory)
        ArchiveHash = GetHash(Archive)
        if (CachedHash := HashCache["Archives"].get(ArchivePath)) is None or (CachedHash != ArchiveHash):
            # Update hash of the file's content
            HashCache["Archives"][ArchivePath] = ArchiveHash
            if not Extracted:
                ArchiveFolderPath = CutDirectory(ArchiveFolder, TroveDirectory)
                Output = os.path.join(ExtractedDirectory, ArchiveFolderPath)
                # Make sure to not blast windows with too many Trove.exe processes
                while len(list(GetTroveProcesses())) >= 100:
                    await sleep(2)
                ExtractArchive(ArchiveFolder, Output)
                ExtractedArchivePaths.append(ArchiveFolderPath)
                Extracted = True

async def ExtractArchives():
    """Setup files for extraction through the use of asynchronous methods to speed up process"""
    print("Extracting changed archives...")
    with Progress() as ExtractionProgress:
        ExtractionProgress.update_to(0, total=len(ArchiveFolders))
        for ArchiveFolder in ArchiveFolders:
            ExtractionProgress.update_to(1, desc=f"{CutDirectory(ArchiveFolder, TroveDirectory):<64}")
            # Extract Archives if one is changed
            await ExtractArchiveFolder(ArchiveFolder)
    print("Waiting Trove processes to finish extracting the files...")
    while True:
        _break = True
        ChildrenProcesses = CurrentProcess.children(recursive=True)
        for ChildProcess in ChildrenProcesses:
            if ChildProcess.pid in StartedProcesses:
                _break = False
                break
        if _break:
            break
        await sleep(5)
    # Ensure Hashes are properly saved
    SaveHashes(TroveDirectory, HashCache)

# Ensure user wants to proceed to give cancellation room
if input("Do you wish to proceed with this extraction? Y | N\n").lower() not in ["y", "yes"]:
    print("Extraction cancelled.")
    os.system("PAUSE")
    quit()

# Quit script if things aren't as expected
if not SanityCheck():
    os.system("PAUSE")
    quit()

async def main():
    """Runs the program itself as an asynchronous method"""
    # Ensure user doesn't lose previous hash data
    HashBackupFile = None
    if HashCache.get("Archives") or HashCache.get("Files"):
        HashBackupFile = f"EAEHashLogBackup_{datetime.now().strftime('%Y-%m-%d_%H.%M')}.json"
        SaveHashes(TroveDirectory, HashCacheBackup, HashBackupFile)
        print(f"Saved previous hashlog to `{HashBackupFile}`, you can change it's name to `EAEHashLog.log` to restore it if you cancel this script midway or it errors.")
    TrackChanges = input("Do you wish to have a separate directory with changes created for this version? Y | N\n").lower() in ["y", "yes"]
    CreatePreviews = False
    if TrackChanges:
        print("Do you want to create PNG previews of the changed blueprints? Y | N")
        print(" - This process can be time and resource consuming")
        print(" - This will not run if there's no changes tracked yet")
        print(" - This will delete all files in `Catalog` diretory")
        CreatePreviews = input().lower() in ["y", "yes"]
    PrepareDirectory(TrackChanges, CreatePreviews)
    # Setup Hash logging for first run
    if TrackChanges:
        if not HashCache.get("Files"):
            await GetExtractedFileHashes()
    # Extract Archives
    await ExtractArchives()
    print("\nAll files have been exported.")
    # Look for changes and move them to the assigned folder
    if TrackChanges:
        if HashCache.get("Files"):
            CheckExtractedFileHashes(CreatePreviews)
        else:
            await GetExtractedFileHashes()
            print("Current file state recorded for future change logging.")
    # Ensure directory doesn't get filled with backup hash logs
    if HashBackupFile:
        os.remove(os.path.join(TroveDirectory, HashBackupFile))

run(main())
os.system("PAUSE")
