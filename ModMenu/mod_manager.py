import os.path as op
from ctypes import (
    Array,
    _Pointer,
    byref,
    c_bool,
    c_char,
    c_char_p,
    create_string_buffer,
    memmove,
    memset,
)
from dataclasses import dataclass, field
from logging import getLogger
from typing import Annotated

import nmspy.data.types as nms
from nmspy.data.xml_types import mdModInfo
from nmspy.decorators import on_fully_booted
from nmspy.shared import unique_counter
from pymhf import Mod, ModState
from pymhf.core.hooking import static_function_hook
from pymhf.core.memutils import get_addressof, map_struct
from pymhf.core.mod_loader import mod_manager as pymhf_mod_manager
from pymhf.extensions.ctypes import c_char_p64

logger = getLogger("ModManager")


class cGcFrontendPageOptions(nms.cGcFrontendPageOptions):
    @static_function_hook("48 89 5C 24 ? 57 48 83 EC ? 48 8B 1D ? ? ? ? 0F B6 F9")
    @staticmethod
    def Exit(a1: Annotated[bool, c_bool]):
        ...


@dataclass
class ModManagerState(ModState):
    mod_manager: nms.cGcModManager | None = None
    normal_mod_info: dict[str, mdModInfo] = field(default_factory=dict)
    disabled_mods: set[str] = field(default_factory=set)
    mod_path_buffers: dict[str, Array[c_char]] = field(default_factory=dict)
    mod_page_id: int | None = None
    nmspy_page_id: int | None = None


def make_mod_description(
    mod_authors: str | list[str],
    mod_description: str,
    mod_version: str | None,
    included_mods: list[mdModInfo] | None = None,
):
    """Create a mod description based on the provided info.
    ``included_mods`` will likely only be provided by EXML mods."""
    description_parts = []
    if mod_authors:
        description = "Author"
        if isinstance(mod_authors, list):
            split_authors = mod_authors
        else:
            split_authors = mod_authors.split(",")
        if len(split_authors) > 1:
            description += "s"
        description += ": "
        description += ", ".join([author.strip() for author in split_authors])
        description_parts.append(description)
    if mod_version:
        description_parts.append(f"Version: {mod_version}")
    if mod_description:
        description_parts.append(f"Description: {mod_description}")
    if included_mods:
        # Loop over included mods and add the details to the text.
        if included_mods:
            description_parts.append("Included mods:")
        for mod in included_mods:
            if isinstance(mod_authors, list):
                split_authors = mod_authors
            else:
                split_authors = mod_authors.split(",")
            authors = ", ".join([author.strip() for author in split_authors])
            description_parts.append(f" - {mod.Name} ({mod.Version}) by {authors}")
    return "\n".join(description_parts)


class ModManager(Mod):
    __author__ = "monkeyman192"
    __description__ = "Adds a built-in mod manager to the options pages"
    __version__ = "0.1"

    state = ModManagerState()

    def __init__(self):
        super().__init__()
        if not self.state.disabled_mods:
            self.state.disabled_mods = set()
        self.cached_audio_ptr = None
        # Set the page id's if they haven't already been set.
        # Offset by the number of vanilla options so that we can always ensure that the id never coincides
        # with a vanilla page.
        if self.state.mod_page_id is None:
            self.state.mod_page_id = unique_counter.get() + len(nms.enums.eOptionsMenu)
        if self.state.nmspy_page_id is None:
            self.state.nmspy_page_id = unique_counter.get() + len(nms.enums.eOptionsMenu)

    @on_fully_booted
    def fully_booted(self):
        self.state.mod_manager = map_struct(nms.cGcModManager.GetInstance(), nms.cGcModManager)

    @nms.cTkFileSystem.LoadModDirectory.after
    def after_load_mod_directory(
        self,
        this: _Pointer[nms.cTkFileSystem],
        lpacPath: c_char_p64,
        lpaacDirectoryNamesOut: _Pointer[c_char_p64],
        liMaxDirectories: int,
        liMaxStringSize: int,
        a6: int,
        _result_: int,
    ):
        if str(lpacPath) == "MODS/":
            mod_meta = {}
            addresses_to_move_stuff_to = []
            if lpaacDirectoryNamesOut:
                for i in range(_result_):
                    res = lpaacDirectoryNamesOut[i]
                    mod_name = str(res).lower()
                    if str(res).startswith("."):
                        # Get the address and put it in the list. Also clear the value.
                        addresses_to_move_stuff_to.append(int(res.value))
                        memset(int(res.value), 0, 0x80)
                    else:
                        mod_dir = op.join(str(this.contents.mpData.contents.mWorkingRoot), "MODS", mod_name)
                        # Read the modinfo.exml file as a demo.
                        if op.exists(modinfo := op.normpath(op.join(mod_dir, "ModInfo.exml"))):
                            mod_meta[mod_name] = mdModInfo.read(modinfo)
                # Now, loop over the indexes backwards and copy the data into the free addresses.
                for i in range(len(addresses_to_move_stuff_to)):
                    memmove(
                        addresses_to_move_stuff_to[i],
                        int(lpaacDirectoryNamesOut[_result_ - i - 1].value),
                        0x80,
                    )
                _result_ -= len(addresses_to_move_stuff_to)
            self.state.normal_mod_info = mod_meta
        return _result_

    @property
    def current_selected_page(self):
        idx = nms.GcFrontendPageOptions.mOpenMenuIndex.value >> 8
        if idx in (1, 2):
            return nms.GcFrontendPageOptions.mOpenMenus[idx - 1].contents.meType
        else:
            return None

    @nms.cGcOptionsPageUI.FinalizePage.before
    def pre_page_finalization(self, this, unknown1, unknown2):
        if self.current_selected_page == 6:
            # Add option for normal mods.
            mod_str1 = c_char_p(b"UI_OPTIONS_MODS_L")
            mod_desc1 = c_char_p(b"UI_OPTIONS_MODS_DESC")
            button_params1 = nms.cGcButtonOptions.new_empty()
            button_params1.mbRequireLongPress = False
            if nms.cGcOptionsPageUI.Button(
                this,
                get_addressof(mod_str1),
                get_addressof(mod_desc1),
                byref(button_params1),
            ):
                nms.cGcFrontendPageOptions.RequestOptionsPage(self.state.mod_page_id, False)

            # Add options for NMS.py mods.
            mod_str2 = c_char_p(b"UI_OPTIONS_NMSPY_MODS_L")
            mod_desc2 = c_char_p(b"UI_OPTIONS_NMSPY_MODS_DESC")
            button_params2 = nms.cGcButtonOptions.new_empty()
            button_params2.mbRequireLongPress = False
            if nms.cGcOptionsPageUI.Button(
                this,
                get_addressof(mod_str2),
                get_addressof(mod_desc2),
                byref(button_params2),
            ):
                nms.cGcFrontendPageOptions.RequestOptionsPage(self.state.nmspy_page_id, False)

    def DoNMSpyModList(self, lpOptionsPage: _Pointer[nms.cGcFrontendPageOptions]):
        """Generate the page for NMS.py mods. This will be a separate function to the normal mod page in case
        we want to have different things on them."""
        if self.state.mod_manager is not None:
            mod_text = c_char_p(b"UI_OPTIONS_NMSPY_MODS")
            nms.cGcOptionsPageUI.Header(
                lpOptionsPage, get_addressof(mod_text), nms.enums.cGcOptionsUIHeaderIcons.Cloud
            )

            for mod_name, mod in pymhf_mod_manager.mods.items():
                if mod_name.startswith("_INTERNAL_"):
                    continue
                p_enabled = get_addressof(c_char_p(b"UI_ENABLED"))
                p_disabled = get_addressof(c_char_p(b"UI_DISABLED"))
                bool_params = nms.cGcBooleanOptions.new_empty()
                bool_params.mpacEnabledString = c_char_p64(p_enabled)
                bool_params.mpacDisabledString = c_char_p64(p_disabled)

                text = c_char_p(str(mod_name).encode())
                description = c_char_p(
                    make_mod_description(mod.__author__, mod.__description__, mod.__version__).encode()
                )
                new_mod_state = nms.cGcOptionsPageUI.Boolean(
                    lpOptionsPage,
                    get_addressof(text),
                    get_addressof(description),
                    int(not mod._disabled),
                    1,
                    byref(bool_params),
                )
                if int(not new_mod_state) != mod._disabled:
                    if new_mod_state is True:
                        pymhf_mod_manager.enable(mod_name)
                    else:
                        if mod_name == self._mod_name:
                            logger.info("Disabling self...")
                            # In this case, go back to the normal options page.
                            cGcFrontendPageOptions.Exit(False)
                        pymhf_mod_manager.disable(mod_name)
        nms.cGcOptionsPageUI.FinalizePage(lpOptionsPage, False, True)

    def reload_globals(self):
        mdm = map_struct(nms.cTkMetaDataManager.GetInstance(), nms.cTkMetaDataManager)
        mdm.ReloadGlobals()

    def DoModList(self, lpOptionsPage: _Pointer[nms.cGcFrontendPageOptions]):
        if self.state.mod_manager is not None:
            mod_text = c_char_p(b"UI_OPTIONS_MODS")
            nms.cGcOptionsPageUI.Header(
                lpOptionsPage, get_addressof(mod_text), nms.enums.cGcOptionsUIHeaderIcons.Cloud
            )

            for mod in self.state.mod_manager.mLoadedMods:
                mod_name = str(mod.mSavedData.Name)
                if mod_info := self.state.normal_mod_info.get(mod_name.lower()):
                    description = c_char_p(
                        make_mod_description(
                            mod_info.Authors, mod_info.Description, mod_info.Version, mod_info.IncludedMods
                        ).encode()
                    )
                else:
                    description = c_char_p(str(mod_name).encode())
                p_enabled = get_addressof(c_char_p(b"UI_ENABLED"))
                p_disabled = get_addressof(c_char_p(b"UI_DISABLED"))
                bool_params = nms.cGcBooleanOptions.new_empty()
                bool_params.mpacEnabledString = c_char_p64(p_enabled)
                bool_params.mpacDisabledString = c_char_p64(p_disabled)

                text = c_char_p(str(mod_name).encode())
                new_mod_state = nms.cGcOptionsPageUI.Boolean(
                    lpOptionsPage,
                    get_addressof(text),
                    get_addressof(description),
                    int(mod.mSavedData.Enabled),
                    1,
                    byref(bool_params),
                )
                if bool(new_mod_state) != mod.mSavedData.Enabled:
                    curr_mod_path = f"MODS/{mod.mSavedData.Name}"
                    mod.mSavedData.Enabled = bool(new_mod_state)
                    self.state.mod_manager.WriteSettings(True)
                    if bool(new_mod_state) is False:
                        # If we are disabling a mod, remove it from the list.
                        for i, mod_path in enumerate(nms.tkMetaData.mgModFolderList):
                            if str(mod_path) == curr_mod_path:
                                del nms.tkMetaData.mgModFolderList[i]
                                self.state.disabled_mods.add(curr_mod_path)
                                # Release the reference to the buffer if there is one.
                                if curr_mod_path in self.state.mod_path_buffers:
                                    del self.state.mod_path_buffers[curr_mod_path]
                                break
                    else:
                        # Add the mod back in.
                        encoded_path = curr_mod_path.encode() + b"\x00"
                        buffer = create_string_buffer(encoded_path)
                        self.state.mod_path_buffers[curr_mod_path] = buffer
                        p_curr_mod_path = get_addressof(buffer)
                        self.state.disabled_mods.discard(curr_mod_path)
                        nms.cTkMetaData.mgModFolderList.append(c_char_p64(p_curr_mod_path))
                    self.reload_globals()
        nms.cGcOptionsPageUI.FinalizePage(lpOptionsPage, False, True)

    @nms.cGcOptionsPageUI.EndPage.before
    def handle_options_page(self, lpOptionsPage: _Pointer[nms.cGcFrontendPageOptions]):
        if self.current_selected_page == self.state.mod_page_id:
            self.DoModList(lpOptionsPage)
        if self.current_selected_page == self.state.nmspy_page_id:
            self.DoNMSpyModList(lpOptionsPage)

    @nms.cGcFrontendPage.Confirm.before
    def before_confirm(
        self,
        this: "_Pointer[nms.cGcFrontendPage]",
        lpLayer: _Pointer[nms.cGcNGuiLayer],
        lbInstant: bool,
        lbSlow: bool,
        lCustomConfirmationSound: _Pointer[nms.TkAudioID],
        lbIsSetTouchButton: bool,
        lbSkipSlowForTouch: bool,
    ):
        if self.cached_audio_ptr is None:
            self.cached_audio_ptr = lCustomConfirmationSound

    @nms.cGcFrontendPageOptions.DoGameSwitcher.before
    def before_ingame_options(self, this: _Pointer[nms.cGcFrontendPage]):
        if this and (opts := this.contents):
            # Handle the "normal" mod menu.
            mID = nms.cTkHashedNGuiElement("BUTTON_MODS", nms.enums.eNGuiGameElementType.Layer)
            _text_layer = opts.mpPage.contents.FindElementRecursive(
                byref(mID),
                nms.enums.eNGuiGameElementType.Layer,
            )
            if _text_layer:
                layer = map_struct(_text_layer, nms.cGcNGuiLayer)
                white = nms.basic.TkID0x10("WHITE")
                white_address = layer.GetLayer(byref(white), True)
                clickable = map_struct(white_address, nms.cGcNGuiLayer)
                if self.cached_audio_ptr is not None:  # noqa
                    if opts.Confirm(byref(clickable), True, False, self.cached_audio_ptr, False, True):
                        nms.cGcFrontendPageOptions.RequestOptionsPage(self.state.mod_page_id, False)

            # If it's not there, then we don't show the nmspy nutton.
            mID = nms.cTkHashedNGuiElement("BUTTON_NMSPY", nms.enums.eNGuiGameElementType.Layer)
            _text_layer = opts.mpPage.contents.FindElementRecursive(
                byref(mID),
                nms.enums.eNGuiGameElementType.Layer,
            )
            if _text_layer:
                layer = map_struct(_text_layer, nms.cGcNGuiLayer)
                white = nms.basic.TkID0x10("WHITE")
                white_address = layer.GetLayer(byref(white), True)
                clickable = map_struct(white_address, nms.cGcNGuiLayer)
                if self.cached_audio_ptr is not None:  # noqa
                    if opts.Confirm(byref(clickable), True, False, self.cached_audio_ptr, False, True):
                        nms.cGcFrontendPageOptions.RequestOptionsPage(self.state.nmspy_page_id, False)
