# TheAmiiboDoctor
Python script for fixing common errors with Amiibo NFC and BIN files.

#### NOTE: 
- This fixes CT in SN3, UID Mismatch, BCC0, BCC1, DLB, CFG0, CFG1, PWD and PACK issues.
- This does not require any keys to fix these issues. 
- This script backs up any files it will modify before modifying. 
- This script recursively searches for nfc and bin files.
- Can also convert V2 and V3 Flipper NFC files to V4. (Which is what all the testing was done around)
- No Jabs Required, just a few pokes.

**WORKS ONLY FOR NTAG215, NOT FOR THE NTAG I2C Plus 2K**

**Usage:**

1. Dry run **(safe preview, recommended)**:
`python3 TheAmiiboDoctor.py ./ameebo_files`

2. Convert v4 (safe preview):
`python3 TheAmiiboDoctor.py ./ameebo_files --convert-v4`

3. Convert Only:
`python3 TheAmiiboDoctor.py ./ameebo_files --fix --convert-v4 --no-uid --no-bcc --no-password --no-pack --no-dlb --no-cfg`

4. Convert and Fix **(recommended)**:
`python3 TheAmiiboDoctor.py ./ameebo_files --fix --convert-v4`

```
usage: TheAmiiboDoctor.py [-h] [--fix] [--convert-v4] [--no-uid] [--no-bcc] [--no-password] [--no-pack] [--no-dlb] [--no-cfg] directory

Fix NTAG215 NFC and BIN files for Flipper to Switch amiibo emulation

positional arguments:
  directory      Directory containing NFC and BIN files

options:
  -h, --help     show this help message and exit
  --fix          Actually fix files (default is dry run)
  --convert-v4   Convert V2/V3 NFC files to V4 format
  --no-uid       Skip UID fixes
  --no-bcc       Skip BCC fixes
  --no-password  Skip password fixes
  --no-pack      Skip PACK fixes
  --no-dlb       Skip DLB fixes
  --no-cfg       Skip CFG0/CFG1 fixes
```

## Special Thanks

I would like to thank **[@equipter](https://github.com/equipter)** for all the help understanding 0x88 in the 4th position of the UID as well as CT analysis, BCC0 and BCC1 calculations
