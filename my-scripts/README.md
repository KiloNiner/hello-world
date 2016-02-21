# Scripts

a bunch of script authored by me through the years.

### add-killbit.ps1
Remotely add IE killbits. Requires access to the remote registry service.

### archiver.vbs
Script for compressing and removing logfiles

Utilizes any one of a number og external compressors as the builtin in
Windows has a tendency to freeze on loaded systems.

Adds all files for a single day into a dated archive.

Arguments:
* folder - folder to search for source files to compress and delete
* days to keep files - ignore files younger than this

### check-customerrors.ps1
This script will expose a function that enumerates through subdirectories
spots web.config files and then checks for the /configuration/system.web/
customerrors/@mode value to determine whether custom errors are shown in
place of detailed ASP.NET errors.

### checkforoldfiles.vbs
This script will run through a folder, write the names of any files that are
older than 90 minutes to stdout and exit with an exitcode 1 if any are found.
will exit with error code 0 if everything looks good.

### get-randomstring.ps1
This script creates a cryptographically random string of the given byte length,
good for service account passwords.
The default length of 32 equates to 256 bits of entropy.

### riddler.ps1
Client for the riddler.io API, made in PowerShell.

### update-dns.vbs
This script will look through all adapters on the system enabled for IP
traffic, checks if they use a predefined set of nameservers and updates their
configuration if they do, based off one of several preferred orders.
