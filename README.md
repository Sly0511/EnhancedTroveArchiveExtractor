# EnhancedTroveArchiveExtractor
This project aims at automating the process of extraction of Trove Game Files and speeding up further extractions by using Hashing to filter unchanged files

## Important note
Windows is quite annoying with it's anti malware software, it may slow down significantly the extraction process to have antivirus on, it is not required to disable, but doing so will speed up the extraction process.

#### You can contact developer [here](https://trove.slynx.xyz/support) [Sly#0511]

### [Download Executable Here](https://github.com/Sly0511/EnhancedTroveArchiveExtractor/releases/latest)

## Why use this tool?
 - This tool enabled faster extractions than TroveTools.net and average bat file, how?
    - It saves hashes of all archives and checks if they changed to know what needs extraction.
    - It allows concurrency, which means various processes of Trove extracting at the same time instead of waiting for one to finish to start another.
 - This tool also tracks changes across extractions (except file removals, maybe in the future).
 - This tool automatically runs catalog previews (Though this process is quite slow due to Trove.exe loading assets)

All this benefits you because your SSD has limited cycles, and re exporting Trove which is 1Gb over and over, will make your SSD life sorter overtime, this tool simply aims at exporting the least necessary by checking whether files have changed or not before extracting.
Even if you are using an HDD you avoid too much fragmentation done to the disk which slows it down overtime.

## Windows or browser is saying it's a virus
Unfortunately windows is strict with what it wants to run.
The exe file isn't signed with a certificate, so Windows will say it's a virus regardless, unless you have dev certificates in your machine.

Best way around this is:
  - Open Windows Security
  - Go to Virus and Threat Protection
  - Disable Real Time Protection
  - You can reenable once you are done with running the program.
  - Regardless if you forget it will re enable itself shortly, windows will force it on eventually.
