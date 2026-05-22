from __future__ import annotations

import threading
import traceback
from pathlib import Path
from tkinter import filedialog

try:
    import customtkinter as ctk
except ImportError as exc:
    raise RuntimeError("customtkinter is required. Install requirements.txt first.") from exc

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

from dayz_texture_tool.batch import collect_image_files, process_game2pbr_auto, process_game2pbr_files
from dayz_texture_tool.models import BatchResult
from dayz_texture_tool.processors.game2pbr import GAME2PBR_PROCESSORS
from dayz_texture_tool.processors.pbr2dayz import IMAGE_EXTENSIONS, convert_pbr_folder
from dayz_texture_tool.settings import load_settings, save_settings
from dayz_texture_tool.ui.i18n import text


GAME_PROCESSORS = [
    "DF_NRM",
    "DF_MRA",
    "ABI_ORN",
    "SplitColorAlphaProcessor",
    "SplitRGBAProcessor",
    "MergeRGBAProcessor",
    "XYNormalMapProcessor",
    "DirectConvertProcessor",
    "DirectinvertProcessor",
]

PBR_TYPES = ["basecolor", "normal", "roughness", "metallic", "ao"]


class DnDCTk(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if TkinterDnD is not None:
            self.TkdndVersion = TkinterDnD._require(self)


class DayZTextureToolApp(DnDCTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.settings = load_settings()
        self.language = self.settings.language
        self.selected_game_processor = "DF_NRM"
        self.mode_display_to_id: dict[str, str] = {}
        self.game2pbr_files: list[Path] = []
        self.game2pbr_folder: Path | None = None
        self.pbr_folder: Path | None = None
        self.widgets: dict[str, object] = {}
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.current_page = "game"
        self.title(text(self.language, "title"))
        self.geometry("1180x780")
        self.minsize(1040, 700)
        self._build()
        self._apply_language()
        self._load_game_suffix()
        self._load_pbr_suffixes()
        self._update_status_labels()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        self.widgets["title_label"] = ctk.CTkLabel(header, font=ctk.CTkFont(size=20, weight="bold"))
        self.widgets["title_label"].grid(row=0, column=0, padx=(20, 16), pady=12, sticky="w")
        self.widgets["nav"] = ctk.CTkSegmentedButton(header, values=["Game2PBR", "PBR2DayZ", "Settings"], command=self._show_page)
        self.widgets["nav"].grid(row=0, column=1, padx=8, pady=12, sticky="ew")
        self.widgets["nav"].set("Game2PBR")
        self.widgets["lang_button"] = ctk.CTkButton(header, width=110, command=self._toggle_language)
        self.widgets["lang_button"].grid(row=0, column=2, padx=(16, 20), pady=12)
        self.widgets["page_container"] = ctk.CTkFrame(self, fg_color="transparent")
        self.widgets["page_container"].grid(row=1, column=0, padx=20, pady=20, sticky="nsew")
        self.widgets["page_container"].grid_columnconfigure(0, weight=1)
        self.widgets["page_container"].grid_rowconfigure(0, weight=1)
        self.game_tab = self._page("game")
        self.pbr_tab = self._page("pbr")
        self.settings_tab = self._page("settings")
        self._build_game_tab()
        self._build_pbr_tab()
        self._build_settings_tab()
        self._show_page("Game2PBR")

    def _page(self, name: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.widgets["page_container"], fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        self.pages[name] = page
        return page

    def _build_game_tab(self) -> None:
        self.game_tab.grid_columnconfigure(0, weight=7)
        self.game_tab.grid_columnconfigure(1, weight=3)
        self.game_tab.grid_rowconfigure(3, weight=1)
        controls = ctk.CTkFrame(self.game_tab)
        controls.grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        self.widgets["game_processor_label"] = ctk.CTkLabel(controls)
        self.widgets["game_processor_label"].grid(row=0, column=0, padx=14, pady=14, sticky="w")
        self.widgets["game_processor"] = ctk.CTkOptionMenu(controls, values=[], command=self._on_game_mode_change)
        self.widgets["game_processor"].grid(row=0, column=1, padx=10, pady=14, sticky="ew")
        self.widgets["game_files_button"] = ctk.CTkButton(controls, command=self._select_game_files)
        self.widgets["game_files_button"].grid(row=0, column=2, padx=6, pady=14)
        self.widgets["game_folder_button"] = ctk.CTkButton(controls, command=self._select_game_folder)
        self.widgets["game_folder_button"].grid(row=0, column=3, padx=6, pady=14)

        suffix = ctk.CTkFrame(self.game_tab)
        suffix.grid(row=1, column=0, columnspan=2, padx=14, pady=8, sticky="ew")
        suffix.grid_columnconfigure(1, weight=1)
        self.widgets["game_suffix_label"] = ctk.CTkLabel(suffix)
        self.widgets["game_suffix_label"].grid(row=0, column=0, padx=14, pady=14, sticky="w")
        self.widgets["game_suffix"] = ctk.CTkEntry(suffix)
        self.widgets["game_suffix"].grid(row=0, column=1, padx=10, pady=14, sticky="ew")
        self.widgets["game_match_mode"] = ctk.CTkSegmentedButton(suffix, values=["exact", "fuzzy"], command=self._on_game_match_mode_change)
        self.widgets["game_match_mode"].set(self.settings.game_match_mode)
        self.widgets["game_match_mode"].grid(row=0, column=2, padx=10, pady=14)
        self.widgets["game_delete_source"] = ctk.CTkCheckBox(suffix)
        self.widgets["game_delete_source"].grid(row=0, column=3, padx=10, pady=14)
        self.widgets["game_suffix_hint"] = ctk.CTkLabel(suffix, text_color="gray55")
        self.widgets["game_suffix_hint"].grid(row=0, column=4, padx=14, pady=14, sticky="e")

        self.widgets["game_drop"] = self._drop_area(self.game_tab, self._on_game_drop, "drop_files", "drop_files_hint")
        self.widgets["game_drop"].grid(row=2, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="nsew")
        self.widgets["game_pending"] = self._pending_panel(self.game_tab)
        self.widgets["game_pending"].grid(row=2, column=1, padx=(8, 14), pady=8, sticky="nsew")
        self.widgets["game_start_button"] = ctk.CTkButton(self.game_tab, width=188, height=56, font=ctk.CTkFont(size=16, weight="bold"), command=self._start_game2pbr)
        self.widgets["game_start_button"].grid(row=3, column=1, padx=(8, 14), pady=(8, 8), sticky="se")
        self.widgets["game_status"] = ctk.CTkLabel(self.game_tab, text_color="gray55", anchor="w")
        self.widgets["game_status"].grid(row=4, column=0, padx=(18, 8), pady=(4, 14), sticky="ew")
        self.widgets["game_progress"] = ctk.CTkProgressBar(self.game_tab, mode="determinate")
        self.widgets["game_progress"].set(0)
        self.widgets["game_progress"].grid(row=4, column=1, padx=(8, 18), pady=(4, 14), sticky="ew")

    def _build_pbr_tab(self) -> None:
        self.pbr_tab.grid_columnconfigure(0, weight=7)
        self.pbr_tab.grid_columnconfigure(1, weight=3)
        self.pbr_tab.grid_rowconfigure(3, weight=1)
        controls = ctk.CTkFrame(self.pbr_tab)
        controls.grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        self.widgets["normal_label"] = ctk.CTkLabel(controls)
        self.widgets["normal_label"].grid(row=0, column=0, padx=14, pady=14, sticky="w")
        self.widgets["normal_type"] = ctk.CTkSegmentedButton(controls, values=["directx", "opengl"])
        self.widgets["normal_type"].set("directx")
        self.widgets["normal_type"].grid(row=0, column=1, padx=10, pady=14, sticky="ew")
        self.widgets["resolution_label"] = ctk.CTkLabel(controls)
        self.widgets["resolution_label"].grid(row=0, column=2, padx=6, pady=14, sticky="w")
        self.widgets["resolution"] = ctk.CTkOptionMenu(controls, values=["auto", "256", "512", "1024", "2048"], width=120)
        self.widgets["resolution"].set("auto")
        self.widgets["resolution"].grid(row=0, column=3, padx=6, pady=14)
        self.widgets["make_paa"] = ctk.CTkCheckBox(controls)
        self.widgets["make_paa"].grid(row=0, column=4, padx=10, pady=14)
        self.widgets["pbr_delete_source"] = ctk.CTkCheckBox(controls)
        self.widgets["pbr_delete_source"].grid(row=0, column=5, padx=10, pady=14)
        self.widgets["pbr_folder_button"] = ctk.CTkButton(controls, command=self._select_pbr_folder)
        self.widgets["pbr_folder_button"].grid(row=0, column=6, padx=6, pady=14)
        self.widgets["pbr_match_mode"] = ctk.CTkSegmentedButton(controls, values=["exact", "fuzzy"], command=self._on_pbr_match_mode_change)
        self.widgets["pbr_match_mode"].set(self.settings.pbr_match_mode)
        self.widgets["pbr_match_mode"].grid(row=0, column=7, padx=(6, 14), pady=14)

        pbr_suffix = ctk.CTkFrame(self.pbr_tab)
        pbr_suffix.grid(row=1, column=0, columnspan=2, padx=14, pady=8, sticky="ew")
        for index, pbr_type in enumerate(PBR_TYPES):
            pbr_suffix.grid_columnconfigure(index, weight=1)
            label = ctk.CTkLabel(pbr_suffix)
            label.grid(row=0, column=index, padx=8, pady=(12, 2), sticky="w")
            entry = ctk.CTkEntry(pbr_suffix)
            entry.grid(row=1, column=index, padx=8, pady=(2, 12), sticky="ew")
            self.widgets[f"pbr_{pbr_type}_label"] = label
            self.widgets[f"pbr_{pbr_type}"] = entry

        self.widgets["pbr_drop"] = self._drop_area(self.pbr_tab, self._on_pbr_drop, "drop_folder", "drop_folder_hint")
        self.widgets["pbr_drop"].grid(row=2, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="nsew")
        self.widgets["pbr_pending"] = self._pending_panel(self.pbr_tab)
        self.widgets["pbr_pending"].grid(row=2, column=1, padx=(8, 14), pady=8, sticky="nsew")
        self.widgets["pbr_start_button"] = ctk.CTkButton(self.pbr_tab, width=188, height=56, font=ctk.CTkFont(size=16, weight="bold"), command=self._start_pbr2dayz)
        self.widgets["pbr_start_button"].grid(row=3, column=1, padx=(8, 14), pady=(8, 8), sticky="se")
        self.widgets["pbr_status"] = ctk.CTkLabel(self.pbr_tab, text_color="gray55", anchor="w")
        self.widgets["pbr_status"].grid(row=4, column=0, padx=(18, 8), pady=(4, 14), sticky="ew")
        self.widgets["pbr_progress"] = ctk.CTkProgressBar(self.pbr_tab, mode="determinate")
        self.widgets["pbr_progress"].set(0)
        self.widgets["pbr_progress"].grid(row=4, column=1, padx=(8, 18), pady=(4, 14), sticky="ew")

    def _build_settings_tab(self) -> None:
        self.settings_tab.grid_columnconfigure(1, weight=1)
        self.settings_tab.grid_rowconfigure(1, weight=1)
        self.widgets["paa_label"] = ctk.CTkLabel(self.settings_tab)
        self.widgets["paa_label"].grid(row=0, column=0, padx=(18, 8), pady=20, sticky="w")
        self.widgets["paa_path"] = ctk.CTkEntry(self.settings_tab)
        self.widgets["paa_path"].insert(0, self.settings.image_to_paa)
        self.widgets["paa_path"].grid(row=0, column=1, padx=8, pady=20, sticky="ew")
        self.widgets["paa_browse"] = ctk.CTkButton(self.settings_tab, command=self._browse_paa)
        self.widgets["paa_browse"].grid(row=0, column=2, padx=8, pady=20)
        self.widgets["settings_save"] = ctk.CTkButton(self.settings_tab, command=self._save_settings)
        self.widgets["settings_save"].grid(row=0, column=3, padx=(8, 18), pady=20)
        self.widgets["settings_status"] = ctk.CTkLabel(self.settings_tab, text_color="gray55", anchor="w")
        self.widgets["settings_status"].grid(row=1, column=0, columnspan=4, padx=18, pady=12, sticky="new")

    def _drop_area(self, parent, handler, title_key: str, hint_key: str):
        frame = ctk.CTkFrame(parent, corner_radius=12, border_width=2)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.grid(row=0, column=0)
        label = ctk.CTkLabel(content, font=ctk.CTkFont(size=30, weight="bold"))
        label.grid(row=0, column=0, padx=40, pady=(20, 8))
        hint = ctk.CTkLabel(content, text_color="gray55", font=ctk.CTkFont(size=15))
        hint.grid(row=1, column=0, padx=40, pady=(0, 20))
        frame.drop_label = label
        frame.drop_hint = hint
        frame.title_key = title_key
        frame.hint_key = hint_key
        if DND_FILES is not None:
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind("<<Drop>>", handler)
        return frame

    def _pending_panel(self, parent):
        panel = ctk.CTkScrollableFrame(parent, corner_radius=12, label_text="")
        panel.grid_columnconfigure(0, weight=1)
        return panel

    def _mode_label(self, processor: str) -> str:
        return text(self.language, f"mode_{processor}")

    def _refresh_mode_menu(self) -> None:
        values = [self._mode_label(processor) for processor in GAME_PROCESSORS if processor in GAME2PBR_PROCESSORS]
        self.mode_display_to_id = {self._mode_label(processor): processor for processor in GAME_PROCESSORS if processor in GAME2PBR_PROCESSORS}
        self.widgets["game_processor"].configure(values=values)
        self.widgets["game_processor"].set(self._mode_label(self.selected_game_processor))

    def _show_page(self, value: str) -> None:
        page_map = {
            "Game2PBR": "game",
            "PBR2DayZ": "pbr",
            "Settings": "settings",
            text(self.language, "game2pbr"): "game",
            text(self.language, "pbr2dayz"): "pbr",
            text(self.language, "settings"): "settings",
        }
        page = page_map.get(value, value)
        self.current_page = page
        if "nav" in self.widgets:
            display = next((label for label, key in page_map.items() if key == page), "Game2PBR")
            self.widgets["nav"].set(display)
        self.pages[page].tkraise()

    def _toggle_language(self) -> None:
        self._save_current_game_suffix()
        self._save_pbr_suffixes()
        self.language = "en" if self.language == "zh" else "zh"
        self.settings.language = self.language
        save_settings(self.settings)
        self._apply_language()

    def _apply_language(self) -> None:
        self.title(text(self.language, "title"))
        self.widgets["title_label"].configure(text=text(self.language, "title"))
        self.widgets["lang_button"].configure(text=text(self.language, "language"))
        self.widgets["nav"].configure(values=[text(self.language, "game2pbr"), text(self.language, "pbr2dayz"), text(self.language, "settings")])
        nav_values = {"game": text(self.language, "game2pbr"), "pbr": text(self.language, "pbr2dayz"), "settings": text(self.language, "settings")}
        self.widgets["nav"].set(nav_values.get(self.current_page, text(self.language, "game2pbr")))
        self.widgets["game_processor_label"].configure(text=text(self.language, "processor"))
        self.widgets["game_files_button"].configure(text=text(self.language, "select_files"))
        self.widgets["game_folder_button"].configure(text=text(self.language, "select_folder"))
        self.widgets["game_start_button"].configure(text=text(self.language, "start"))
        self.widgets["game_suffix_label"].configure(text=text(self.language, "custom_suffix"))
        self.widgets["game_suffix_hint"].configure(text=text(self.language, "suffix_hint_short"))
        self.widgets["game_delete_source"].configure(text=text(self.language, "delete_source"))
        self.widgets["game_match_mode"].configure(values=[text(self.language, "match_exact"), text(self.language, "match_fuzzy")])
        self.widgets["game_match_mode"].set(text(self.language, f"match_{self.settings.game_match_mode}"))
        self.widgets["normal_label"].configure(text=text(self.language, "normal_type"))
        self.widgets["resolution_label"].configure(text=text(self.language, "resolution"))
        self.widgets["make_paa"].configure(text=text(self.language, "make_paa"))
        self.widgets["pbr_delete_source"].configure(text=text(self.language, "delete_source"))
        self.widgets["pbr_folder_button"].configure(text=text(self.language, "select_folder"))
        self.widgets["pbr_start_button"].configure(text=text(self.language, "start"))
        self.widgets["pbr_match_mode"].configure(values=[text(self.language, "match_exact"), text(self.language, "match_fuzzy")])
        self.widgets["pbr_match_mode"].set(text(self.language, f"match_{self.settings.pbr_match_mode}"))
        self.widgets["paa_label"].configure(text=text(self.language, "image_to_paa"))
        self.widgets["paa_browse"].configure(text=text(self.language, "browse"))
        self.widgets["settings_save"].configure(text=text(self.language, "save"))
        for pbr_type in PBR_TYPES:
            self.widgets[f"pbr_{pbr_type}_label"].configure(text=text(self.language, f"pbr_suffix_{pbr_type}"))
        self._refresh_mode_menu()
        self._apply_drop_text("game_drop")
        self._apply_drop_text("pbr_drop")
        self._render_pending("game_pending", self._game_pending_paths())
        self._render_pending("pbr_pending", self._pbr_pending_paths())
        self._update_status_labels()

    def _apply_drop_text(self, key: str) -> None:
        frame = self.widgets[key]
        frame.drop_label.configure(text=text(self.language, frame.title_key))
        frame.drop_hint.configure(text=text(self.language, frame.hint_key))

    def _mode_value(self, display_value: str) -> str:
        if display_value == text(self.language, "match_fuzzy"):
            return "fuzzy"
        return "exact"

    def _parse_suffix_text(self, value: str) -> list[str]:
        parts = value.replace(";", ",").replace(" ", ",").split(",")
        return [part.strip().lower() for part in parts if part.strip()]

    def _format_suffixes(self, suffixes: list[str]) -> str:
        return ", ".join(suffixes)

    def _save_current_game_suffix(self) -> None:
        if "game_suffix" not in self.widgets:
            return
        self.settings.game_suffixes[self.selected_game_processor] = self._parse_suffix_text(self.widgets["game_suffix"].get())

    def _load_game_suffix(self) -> None:
        suffixes = self.settings.game_suffixes.get(self.selected_game_processor, [])
        self.widgets["game_suffix"].delete(0, "end")
        self.widgets["game_suffix"].insert(0, self._format_suffixes(suffixes))

    def _load_pbr_suffixes(self) -> None:
        for pbr_type in PBR_TYPES:
            entry = self.widgets[f"pbr_{pbr_type}"]
            entry.delete(0, "end")
            entry.insert(0, self._format_suffixes(self.settings.pbr_suffixes.get(pbr_type, [])))

    def _save_pbr_suffixes(self) -> None:
        if "pbr_basecolor" not in self.widgets:
            return
        for pbr_type in PBR_TYPES:
            self.settings.pbr_suffixes[pbr_type] = self._parse_suffix_text(self.widgets[f"pbr_{pbr_type}"].get())

    def _on_game_mode_change(self, display_value: str) -> None:
        self._save_current_game_suffix()
        self.selected_game_processor = self.mode_display_to_id.get(display_value, self.selected_game_processor)
        self._load_game_suffix()
        save_settings(self.settings)

    def _on_game_match_mode_change(self, display_value: str) -> None:
        self.settings.game_match_mode = self._mode_value(display_value)
        save_settings(self.settings)

    def _on_pbr_match_mode_change(self, display_value: str) -> None:
        self.settings.pbr_match_mode = self._mode_value(display_value)
        save_settings(self.settings)

    def _game_pending_paths(self) -> list[Path]:
        if self.game2pbr_folder is not None:
            return collect_image_files(self.game2pbr_folder)
        return list(self.game2pbr_files)

    def _pbr_pending_paths(self) -> list[Path]:
        if self.pbr_folder is None:
            return []
        return sorted(path for path in self.pbr_folder.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)

    def _render_pending(self, key: str, paths: list[Path]) -> None:
        panel = self.widgets[key]
        panel.configure(label_text=text(self.language, "pending_title").format(count=len(paths)))
        for child in panel.winfo_children():
            child.destroy()
        if not paths:
            ctk.CTkLabel(panel, text=text(self.language, "pending_empty"), text_color="gray55", anchor="w").grid(row=0, column=0, padx=8, pady=8, sticky="ew")
            return
        for index, path in enumerate(paths):
            ctk.CTkLabel(panel, text=path.name, anchor="w").grid(row=index, column=0, padx=8, pady=(6, 0), sticky="ew")

    def _update_status_labels(self) -> None:
        if self.game2pbr_folder is not None:
            game_status = text(self.language, "selected_folder").format(path=self.game2pbr_folder)
        elif self.game2pbr_files:
            game_status = text(self.language, "selected_files").format(count=len(self.game2pbr_files))
        else:
            game_status = text(self.language, "status_ready")
        pbr_status = text(self.language, "selected_folder").format(path=self.pbr_folder) if self.pbr_folder is not None else text(self.language, "status_ready")
        self.widgets["game_status"].configure(text=game_status)
        self.widgets["pbr_status"].configure(text=pbr_status)
        self.widgets["settings_status"].configure(text=text(self.language, "settings_ready"))

    def _select_game_files(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.tga *.tif *.tiff *.jpg *.jpeg *.bmp *.dds")])
        self.game2pbr_files = [Path(file) for file in files]
        self.game2pbr_folder = None
        self._render_pending("game_pending", self._game_pending_paths())
        self._update_status_labels()

    def _select_game_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.game2pbr_folder = Path(folder)
            self.game2pbr_files = []
            self._render_pending("game_pending", self._game_pending_paths())
            self._update_status_labels()

    def _select_pbr_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.pbr_folder = Path(folder)
            self._render_pending("pbr_pending", self._pbr_pending_paths())
            self._update_status_labels()

    def _browse_paa(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("ImageToPAA", "ImageToPAA.exe"), ("Executable", "*.exe")])
        if path:
            self.widgets["paa_path"].delete(0, "end")
            self.widgets["paa_path"].insert(0, path)

    def _save_settings(self) -> None:
        self._save_current_game_suffix()
        self._save_pbr_suffixes()
        self.settings.image_to_paa = self.widgets["paa_path"].get()
        self.settings.language = self.language
        save_settings(self.settings)
        self.widgets["settings_status"].configure(text=text(self.language, "saved"))

    def _on_game_drop(self, event) -> None:
        paths = [Path(item) for item in self.tk.splitlist(event.data)]
        folders = [path for path in paths if path.is_dir()]
        files = [path for path in paths if path.is_file()]
        if folders:
            self.game2pbr_folder = folders[0]
            self.game2pbr_files = []
        elif files:
            self.game2pbr_files = files
            self.game2pbr_folder = None
        self._render_pending("game_pending", self._game_pending_paths())
        self._update_status_labels()

    def _on_pbr_drop(self, event) -> None:
        paths = [Path(item) for item in self.tk.splitlist(event.data)]
        folders = [path for path in paths if path.is_dir()]
        if folders:
            self.pbr_folder = folders[0]
            self._render_pending("pbr_pending", self._pbr_pending_paths())
            self._update_status_labels()

    def _start_game2pbr(self) -> None:
        if self.game2pbr_folder is None and not self.game2pbr_files:
            self.widgets["game_status"].configure(text=text(self.language, "no_input"))
            return
        self._save_current_game_suffix()
        save_settings(self.settings)
        self._start_progress("game_progress")
        delete_source = bool(self.widgets["game_delete_source"].get())
        if self.game2pbr_folder is not None:
            self._run_async(lambda: process_game2pbr_auto(self.game2pbr_folder, self.settings.game_suffixes, self.settings.game_match_mode, delete_source), "game_status", "game_progress")
            return
        self._run_async(lambda: process_game2pbr_files(self.game2pbr_files, self.selected_game_processor, delete_source), "game_status", "game_progress")

    def _start_pbr2dayz(self) -> None:
        if self.pbr_folder is None:
            self.widgets["pbr_status"].configure(text=text(self.language, "no_input"))
            return
        self._save_pbr_suffixes()
        self.settings.image_to_paa = self.widgets["paa_path"].get()
        save_settings(self.settings)
        normal_type = self.widgets["normal_type"].get()
        resolution = self.widgets["resolution"].get()
        make_paa = bool(self.widgets["make_paa"].get())
        delete_source = bool(self.widgets["pbr_delete_source"].get())
        image_to_paa = self.settings.image_to_paa
        self._start_progress("pbr_progress")
        self._run_async(lambda: convert_pbr_folder(self.pbr_folder, normal_type=normal_type, resolution=resolution, make_paa=make_paa, image_to_paa=image_to_paa, patterns=self.settings.pbr_suffixes, match_mode=self.settings.pbr_match_mode, delete_source=delete_source), "pbr_status", "pbr_progress")

    def _start_progress(self, progress_key: str) -> None:
        progress = self.widgets[progress_key]
        progress.configure(mode="indeterminate")
        progress.start()

    def _stop_progress(self, progress_key: str, value: float) -> None:
        progress = self.widgets[progress_key]
        progress.stop()
        progress.configure(mode="determinate")
        progress.set(value)

    def _run_async(self, work, status_key: str, progress_key: str) -> None:
        def runner():
            try:
                result = work()
                self.after(0, lambda: self._show_result(status_key, progress_key, result))
            except Exception:
                error = traceback.format_exc().splitlines()[-1]
                self.after(0, lambda: self._show_error(status_key, progress_key, error))
        threading.Thread(target=runner, daemon=True).start()

    def _show_result(self, status_key: str, progress_key: str, result: BatchResult) -> None:
        self._stop_progress(progress_key, 1.0 if result.success else 0.0)
        message = text(self.language, "done").format(ok=result.succeeded, fail=result.failed, skip=result.skipped)
        outputs = len(result.outputs)
        if outputs:
            message = f"{message} {text(self.language, 'outputs').format(count=outputs)}"
        self.widgets[status_key].configure(text=message)

    def _show_error(self, status_key: str, progress_key: str, error: str) -> None:
        self._stop_progress(progress_key, 0.0)
        self.widgets[status_key].configure(text=error)
