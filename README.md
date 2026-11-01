# NMS.py Mod repo

This will be a collection of simple mods for [NMS.py](https://github.com/monkeyman192/NMS.py) which provide various functionalities which may be considered "core" to enhancing the game with NMS.py

## Contents

### Mod Menu

This mod provides an in-game menu for mods - both "traditional" and NMS.py mods which allow you to enable and disable the mods while the game is running.

## General Installation Guide

1. Place any mods you want (as a whole folder) in the `MODS` directory of the game, the same way you would any other "traditional" EXML based mod. These mods often contain EXML/MXML files and are a combination of traditional modding and memory-based modding.
2. Ensure you have python installed on your computer. The version must be 3.10 or above, 64 bit, and should be installed from the official python website rather than the Microsoft store.
3. Install `NMS.py`:
    - **If you are unfamiliar with python**: Run `python -m pip install nmspy`.
    - **If you are familiar with python/virtual environments**: Under a venv (eg. with `uv`) install the [nmspy](https://pypi.org/project/NMSpy/) package. This will install `pymhf` as a command which can be run within the virtual env. If you add the `Scripts` folder of the venv to your system path you can then call the `pymhf` command from anywhere.
4. Run NMS via the command (run in a console): `pymhf run nmspy`
5. The first time you run this it will prompt you to set up some config values. The only one you'll need to specify is the mod directory which you want to specify as the `MODS` directory under the `GAMEDATA` folder.
    - **Note**: If you have the GOG version of the game instead of steam, you'll need to configure the "binary path" value to be the full path of the exe on your computer, otherwise NMS.py will try and run the game via steam.
6. (Optional) If you want, you can create a shortcut on your desktop with the path `pymhf run nmspy` and name `NMS - Modded`. Double clicking on the shortcut will launch the game modded.

**Note**: Running the game from `pymhf` will NOT start steam and will throw an error if you try and run it without steam already being started. Always make sure steam is already started before running the game this way.

## Contribution/Attribution

The mods contained within this repo are designed to be both convenient tools for the community, both in terms of being useful mods, but also being example of general "best practice" in terms of how to write mods using NMS.py.

I openly welcome contributions to these mods so if you see an improvement that you think would benefit everyone, please open a PR to make the changes (and possibly associated changes in NMS.py as well!)

PR's to contribute translations would also be greatly appreciated.
