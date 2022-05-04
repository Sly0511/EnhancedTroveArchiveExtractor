import os
import re
import shutil
import subprocess
import sys
from asyncio import create_task, run, sleep
from datetime import datetime
from shutil import copy
from pathlib import Path

from psutil import Process

from utils import *

# Intro Text
print(
"""
Welcome to Enhanced Trove Archive Extractor

- This tool extracts all game files it finds in current working directory
- The more files and folders you have the slower this process becomes
- The program will by default ignore all directories with ´extracted´ in their name
- This tool will create a file called `EAEHashLog.json` to store file states and avoid re extracting unchanged files (speeds up extractions of following updates)
"""
)

# Get Processor Information
CPUCount = os.cpu_count()
# Process Management
CurrentProcess = Process()
StartedProcesses = []
# Directory setup
TroveDirectory = os.path.dirname(sys.executable)
TroveEXE = os.path.join(TroveDirectory, "Trove.exe")
#Manifest = os.path.join(TroveDirectory, "manifest.txt")
ExtractedDirectory = os.path.join(TroveDirectory, "Extracted")
ChangedDirectory = os.path.join(TroveDirectory, "Changed")
# Load previous logged hashes and create a backup for user cancellation
HashCache = LoadHashes(TroveDirectory)
HashCacheBackup = LoadHashes(TroveDirectory)
# Index all folders with index files
print("\nIndexing archives...")
ArchiveFolders = list(FindTroveArchiveFolders(TroveDirectory))
print(f"Found {len(ArchiveFolders)} Archive indexes.")
# This is a cache to avoid checking for changes on all directories
ExtractedArchivePaths = []
ToCatalog = []
CataloguedFiles = []

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
def PrepareDirectory(Changes=False):
    """Ensure necessary folders are created"""
    if not os.path.isdir(ExtractedDirectory):
        CreateDirectory(ExtractedDirectory, True)
    if not os.path.isdir(ChangedDirectory) and Changes:
        CreateDirectory(ChangedDirectory, True)

def GetTroveProcesses():
    """Get all subprocesses that were created by this script"""
    Children = CurrentProcess.children(recursive=True)
    for Child in Children:
        if Child.pid in StartedProcesses:
            yield Child.pid

async def WaitSubprocessDeath():
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
    FileName = os.path.basename(FilePathName)
    Progress.update_to(1, desc=f"{FileName:<64}")
    if HashCache["Files"].get(FilePathName) is None:
        while True:
            try:
                HashCache["Files"][FilePathName] = await AsyncGetHash(File)
                break
            except OSError:
                ...
            except FileNotFoundError:
                break

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
    print("Extracted files hashes were read.")

def CatalogBlueprint(File):
    """Open a Trove.exe subprocess to create blueprint previews"""
    if File not in CataloguedFiles:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        command = f"{TroveEXE} -tool catalog -filter \"{File}\" -dimension \"256\""# -dir \"{Directory}\""
        CMDProcess = subprocess.Popen(
            command,
            cwd=TroveDirectory,
            startupinfo=startupinfo
        )
        CataloguedFiles.append(File)
        StartedProcesses.append(CMDProcess.pid)

async def CheckExtractedFileHashes(Catalog=False):
    """Check new file hashes against stored ones"""
    ChangesDirectory = os.path.join(ChangedDirectory, datetime.now().strftime("%Y-%m-%d_%H-%M"))
    CreateDirectory(ChangesDirectory, True)
    print("Indexing extracted files...")
    ExtractedFiles = list(GetExtractedFiles(ExtractedDirectory))
    with Progress(total=len(ExtractedFiles)) as HashChecking:
        for File in ExtractedFiles:
            FileHash = GetHash(File)
            FileLocation = CutDirectory(File, ExtractedDirectory)
            FileName = os.path.basename(FileLocation)
            FilePath = os.path.dirname(FileLocation)
            HashChecking.update_to(1, desc=f"{FileName:<64}")
            if not ExtractedArchivePaths or FilePath in ExtractedArchivePaths:
                if (OldHash := HashCache["Files"].get(FileLocation)) is None or FileHash != OldHash:
                    HashCache["Files"][FileLocation] = FileHash
                    CreateDirectory(os.path.join(ChangesDirectory, FilePath))
                    NewFile = os.path.join(ChangesDirectory, FileLocation)
                    copy(File, NewFile)
                    if FileName.endswith(".blueprint") and File not in ToCatalog:
                        BlueprintName = re.sub("(?:\[.*\])?\.blueprint", "", Path(File).name)
                        if len(BlueprintName.split("_")) >= 5:
                            ToCatalog.append(re.match("^.*_", BlueprintName).group(0))
                        else:
                            ToCatalog.append(BlueprintName)
    print(f"Changes logged into \"{ChangesDirectory}\"")
    if Catalog:
        print(f"Processor with {CPUCount} logical cores detected, cataloguing will be tuned using this information")
        print("Cataloging changed files...")
        await CatalogChangedFiles(ChangesDirectory)

# Cataloging
async def CatalogChangedFiles(ChangesDirectory):
    CatalogsDirectory = os.path.join(ChangesDirectory, "catalog")
    CreateDirectory(CatalogsDirectory, True)
    shutil.rmtree(CatalogsDirectory, ignore_errors=True)
    BPToCatalog = list(set(ToCatalog))
    with Progress(total=len(BPToCatalog)) as Cataloguing:
        for Blueprint in BPToCatalog:
            Cataloguing.update_to(1, desc=f"{Blueprint.replace('.blueprint', ''):<64}")
            while len(list(GetTroveProcesses())) >= CPUCount-2:
                await sleep(2)
            CatalogBlueprint(Blueprint)
    print("Waiting Trove processes to finish creating catalogs...")
    await WaitSubprocessDeath()
    OriginalCatalog = os.path.join(TroveDirectory, "catalog")
    def CopyCatalogFile(src, dst):
        shutil.copy(src, dst.replace(".blueprint.png", ".png"))
    shutil.copytree(OriginalCatalog, CatalogsDirectory, dirs_exist_ok=True, copy_function=CopyCatalogFile)
    shutil.rmtree(OriginalCatalog, ignore_errors=True)
    print("Changed files were successfully catalogued.")

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
    with Progress(total=len(ArchiveFolders)) as ExtractionProgress:
        for ArchiveFolder in ArchiveFolders:
            ExtractionProgress.update_to(1, desc=f"{CutDirectory(ArchiveFolder, TroveDirectory):<64}")
            # Extract Archives if one is changed
            await ExtractArchiveFolder(ArchiveFolder)
    print("Waiting Trove processes to finish extracting the files...")
    await WaitSubprocessDeath()

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
        print(" - This will delete all files in `catalog` folder")
        CreatePreviews = input().lower() in ["y", "yes"]
    PrepareDirectory(TrackChanges)
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
            await CheckExtractedFileHashes(CreatePreviews)
        else:
            await GetExtractedFileHashes()
            print("Current file state recorded for future change logging.")
    # Ensure directory doesn't get filled with backup hash logs
    SaveHashes(TroveDirectory, HashCache)
    if HashBackupFile:
        os.remove(os.path.join(TroveDirectory, HashBackupFile))

try:
    run(main())
except Exception as e:
    print(f"An Error Occured\n{e}")
os.system("PAUSE")
