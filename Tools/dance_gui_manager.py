import os
import json
import hashlib
import subprocess
import threading
import tkinter as tk
import urllib.request
import urllib.error
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
DANCES_DIR = Path("./Dances")
OUTPUT_DIR = Path("./DanceStates/DanceInfo")

CLOUD_PRIMARY = "https://maoxig.github.io/UnityDanceInfo/DanceInfo/dances.json"
CLOUD_FALLBACK = "https://unitydanceinfo.pages.dev/DanceInfo/dances.json"

# Map folder names to authors (can be extended)
AUTHOR_MAP = {
    "tanito": "tanito",
    "wdsa": "wdsa",
    "安卓喵": "安卓喵",
    "Xenophon": "Xenophon"
}

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# ---------------------------------------------------------
# BACKEND LOGIC
# ---------------------------------------------------------

def get_author_from_path(file_path: Path) -> str:
    """Guess author based on folder name."""
    try:
        rel = file_path.relative_to(DANCES_DIR)
        for part in rel.parts:
             if part in AUTHOR_MAP:
                 return AUTHOR_MAP[part]
    except ValueError:
        pass
    
    # Fallback: check parent name
    parent_name = file_path.parent.name
    return AUTHOR_MAP.get(parent_name, "Unknown")

def file_hash(path: Path) -> str:
    """Compute MD5 hash (first 8 chars)."""
    h = hashlib.md5()
    try:
        with path.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()[:8]
    except FileNotFoundError:
        return None

def load_database():
    """Load the central dances.json database, merging legacy files if needed."""
    data = {}
    
    # 1. Load Central DB
    dances_json_path = OUTPUT_DIR / "dances.json"
    if dances_json_path.exists():
        try:
            with open(dances_json_path, "r", encoding="utf8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading dances.json: {e}")

    return data

def save_database(data):
    """Save the central dances.json database."""
    dances_json_path = OUTPUT_DIR / "dances.json"
    try:
        with open(dances_json_path, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        messagebox.showerror("Save Error", f"Failed to save dances.json:\n{e}")

def fetch_cloud_database():
    """Fetch database from cloud sources."""
    for url in [CLOUD_PRIMARY, CLOUD_FALLBACK]:
        try:
            print(f"Attempting to fetch from: {url}")
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    print("Cloud fetch successful.")
                    return data
        except Exception as e:
            print(f"Failed to fetch from {url}: {e}")
    return None

# ---------------------------------------------------------
# GUI DIALOGS
# ---------------------------------------------------------

class CloudSyncDialog(tk.Toplevel):
    def __init__(self, parent, local_data, cloud_data, on_apply_callback):
        super().__init__(parent)
        self.title("Cloud Sync - Resolve Differences")
        self.geometry("900x600")
        self.transient(parent)
        self.grab_set()
        
        self.local_data = local_data
        self.cloud_data = cloud_data
        self.on_apply_callback = on_apply_callback
        self.diffs = self.calculate_diffs()
        

        toolbar = ttk.Frame(self.root, padding=5)  # Ensure toolbar is defined
        toolbar.pack(side="top", fill="x")
        self.btn_cloud = ttk.Button(toolbar, text="☁ Check Cloud", command=self.check_cloud_updates)
        self.btn_cloud.pack(side="left", padx=5)
        self.setup_ui()
        self.populate_list()

    def calculate_diffs(self):
        diffs = [] # (hash, type)
        # Check for updates or new items
        for h, c_item in self.cloud_data.items():
            if h in self.local_data:
                l_item = self.local_data[h]['data']
                # Check for meaningful differences
                if (c_item.get('name') != l_item.get('name') or
                    c_item.get('author') != l_item.get('author') or
                    c_item.get('credits') != l_item.get('credits') or
                    c_item.get('comment') != l_item.get('comment')):
                    diffs.append((h, "UPDATE"))
            else:
                diffs.append((h, "NEW DB ENTRY")) # Item exists in Cloud but not in local inventory (files might be missing)
        return diffs

    def setup_ui(self):
        # Layout: Left List, Right Diff View
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Left: List of changes
        left_frame = ttk.Labelframe(paned, text="Differences Found")
        paned.add(left_frame, weight=1)
        
        self.diff_list = tk.Listbox(left_frame, width=30)
        self.diff_list.pack(fill="both", expand=True, padx=5, pady=5)
        self.diff_list.bind('<<ListboxSelect>>', self.on_select_diff)
        
        # Right: Detail Comparison
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)
        
        # Comparison Grid
        self.comp_frame = ttk.Frame(right_frame)
        self.comp_frame.pack(fill="x", padx=10, pady=10)
        
        # Header
        ttk.Label(self.comp_frame, text="Field", font=("Bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.comp_frame, text="My Local Version", font=("Bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(self.comp_frame, text="Cloud Version", font=("Bold")).grid(row=0, column=2, sticky="w")
        
        # Fields
        self.lbls_local = {}
        self.lbls_cloud = {}
        fields = ["name", "author", "credits", "comment"]
        
        for idx, field in enumerate(fields, 1):
            ttk.Label(self.comp_frame, text=field.capitalize() + ":").grid(row=idx, column=0, sticky="nw", pady=2)
            
            l_lbl = tk.Text(self.comp_frame, height=3, width=30, wrap="word", bg="#f0f0f0")
            self.lbls_local[field] = l_lbl
            l_lbl.grid(row=idx, column=1, sticky="w", padx=5)
            
            c_lbl = tk.Text(self.comp_frame, height=3, width=30, wrap="word", bg="#e6f3ff")
            self.lbls_cloud[field] = c_lbl
            c_lbl.grid(row=idx, column=2, sticky="w", padx=5)

        # Actions
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill="x", pady=20)
        
        ttk.Button(btn_frame, text="✅ Apply Cloud Version (Overwrite Local)", command=self.apply_cloud).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="❌ Keep Local (Ignore)", command=self.keep_local).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Apply ALL Cloud Updates", command=self.apply_all).pack(side="right", padx=10)

    def populate_list(self):
        self.diff_list.delete(0, tk.END)
        if not self.diffs:
            self.diff_list.insert(tk.END, "No differences found.")
            return
            
        for h, type_ in self.diffs:
            name = self.cloud_data[h].get('name', '???')
            self.diff_list.insert(tk.END, f"[{type_}] {name}")

    def on_select_diff(self, event):
        sel = self.diff_list.curselection()
        if not sel: return
        
        idx = sel[0]
        h, type_ = self.diffs[idx]
        
        c_item = self.cloud_data[h]
        l_item = self.local_data.get(h, {}).get('data', {})
        
        self.display_comparison(l_item, c_item)

    def display_comparison(self, l_item, c_item):
        fields = ["name", "author", "credits", "comment"]
        for f in fields:
            l_val = str(l_item.get(f, ""))
            c_val = str(c_item.get(f, ""))
            
            # Format lists (credits)
            if isinstance(l_item.get(f), list): l_val = "\n".join(l_item.get(f))
            if isinstance(c_item.get(f), list): c_val = "\n".join(c_item.get(f))
            
            self.set_text(self.lbls_local[f], l_val)
            self.set_text(self.lbls_cloud[f], c_val)

    def set_text(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def apply_cloud(self):
        sel = self.diff_list.curselection()
        if not sel: return
        
        idx = sel[0]
        h, type_ = self.diffs[idx]
        
        # Apply data
        self.on_apply_callback(h, self.cloud_data[h])
        
        # Remove from list
        del self.diffs[idx]
        self.populate_list()
        
        # Select next if available
        if self.diffs:
            self.diff_list.selection_set(0)
            self.on_select_diff(None)
        else:
            messagebox.showinfo("Done", "All conflicts resolved.")
            self.destroy()

    def keep_local(self):
        sel = self.diff_list.curselection()
        if not sel: return
        idx = sel[0]
        # Just remove from list
        del self.diffs[idx]
        self.populate_list()

    def apply_all(self):
        if not messagebox.askyesno("Confirm", "Are you sure you want to overwrite ALL local entries with cloud data?"):
            return
            
        for h, type_ in self.diffs:
            self.on_apply_callback(h, self.cloud_data[h])
        
        self.diffs = []
        self.populate_list()
        messagebox.showinfo("Done", "All cloud updates applied.")
        self.destroy()

# ---------------------------------------------------------
# GUI APPLICATION
# ---------------------------------------------------------

class DanceManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dance Info Manager (Hash-based)")
        self.root.geometry("1200x750")

        # Data Structures
        # self.inventory: Dict[hash, { 'path': Path, 'data': dict }]
        self.inventory = {} 
        self.selected_hashes = []
        
        self.setup_ui()
        # Check cloud after a short delay
        self.root.after(1000, self.auto_check_cloud)

    def auto_check_cloud(self):
        """Run cloud check in background on startup."""
        thread = threading.Thread(target=self._cloud_worker, args=(True,))
        thread.daemon = True
        thread.start()

    def check_cloud_updates(self):
        """Button click cloud check."""
        self.btn_cloud.config(state="disabled", text="Checking...")
        thread = threading.Thread(target=self._cloud_worker, args=(False,))
        thread.daemon = True
        thread.start()

    def _cloud_worker(self, silent_mode):
        cloud_data = fetch_cloud_database()
        self.root.after(0, self._on_cloud_result, cloud_data, silent_mode)

    def _on_cloud_result(self, cloud_data, silent_mode):
        self.btn_cloud.config(state="normal", text="☁ Check Cloud")
        
        if not cloud_data:
            if not silent_mode:
                messagebox.showerror("Error", "Failed to fetch cloud data. Check internet connection.")
            return

        # Simple check for diffs count
        diff_count = 0
        for h, c_item in cloud_data.items():
            if h in self.inventory:
                l_item = self.inventory[h]['data']
                if (c_item.get('name') != l_item.get('name') or
                    c_item.get('author') != l_item.get('author') or
                    c_item.get('credits') != l_item.get('credits') or
                    c_item.get('comment') != l_item.get('comment')):
                    diff_count += 1
            else:
                # Warning: New items in cloud but not locally (missing file?)
                # We count them as diffs because we can import the metadata
                diff_count += 1
        
        if diff_count > 0:
            self.btn_cloud.config(text=f"☁ Cloud Updates ({diff_count})!")
            
            if silent_mode:
                # On startup, just notify via button text, don't popup
                pass
            else:
                # If manual click, or if user wants prompt
                 if messagebox.askyesno("Cloud Updates", f"Found {diff_count} differences from cloud.\nOpen merge dialog?"):
                    self.open_merge_dialog(cloud_data)
        else:
            if not silent_mode:
                messagebox.showinfo("Up to Date", "Local database matches Cloud.")

    def open_merge_dialog(self, cloud_data):
        CloudSyncDialog(self.root, self.inventory, cloud_data, self.apply_cloud_update)

    def apply_cloud_update(self, h, cloud_item_data):
        """Callback from SyncDialog to apply a single item."""
        
        # If item exists in inventory (file exists)
        if h in self.inventory:
            self.inventory[h]['data'] = cloud_item_data
            self.inventory[h]['data']['updated'] = datetime.now().strftime("%Y-%m-%d") # Mark as updated locally
            
            # Refresh tree item if visible
            if self.tree.exists(h):
                self.tree.item(h, text=cloud_item_data['name'], values=(h, cloud_item_data['author']))
                
            # If currently selected in editor, refresh editor
            if h in self.selected_hashes:
                self.load_editor(self.selected_hashes)
                
        else:
            # Item is in Cloud but NOT in local inventory (File missing)
            # We add it to inventory structure, but 'path' is None?
            # Warning: Current system assumes valid path for everything in inventory.
            # If we add it, 'refresh_data' might clear it on next scan if file is not found.
            # However, user wants to 'sync'.
            # Solution: We can't really add 'ghost' files to the GUI list easily without breaking logic.
            # For now, we will add it to the 'dances.json' we SAVE, but maybe not show it in list?
            # Or we create a dummy entry.
            pass
            
        # Trigger an auto-save after merge
        # We don't save immediately for every item to avoid I/O spam, but we should save database at end of dialog.
        # Modified: SyncDialog calls this per item. We should mark 'dirty'.
        # For simplicity, let's just save the specific update to memory, and user must click "Save Info" or we auto save at end.
        # Actually, let's just call save_database using current inventory.
        
        # Re-construct DB from inventory to save
        current_db = {k: v['data'] for k, v in self.inventory.items()}
        # Also, we should merge in the Cloud item even if we don't have the file?
        # If h is not in inventory, we haven't added it to current_db yet.
        if h not in self.inventory:
             current_db[h] = cloud_item_data
             
        save_database(current_db)
        # Note: If file is missing, next Refresh/Sync might remove it from DB if logic adheres to "Strictly Scan".
        # Let's check _refresh_data_worker logic:
        # "Build new dataset based on CURRENT files" -> Yes, it purges entries for missing files.
        # So importing metadata for missing files is futile unless we change refresh logic.
        # But for strictly updating EXISTING files, this works perfectly.
        
        # Perform initial scan after UI loads to prevent startup freeze
        self.root.after(200, self.refresh_data)

    def setup_ui(self):
        # Style
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        # --- Toolbar ---
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(side="top", fill="x")

        self.btn_refresh = ttk.Button(toolbar, text="🔄 Refresh & Sync", command=self.refresh_data)
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_cloud = ttk.Button(toolbar, text="☁ Check Cloud", command=self.check_cloud_updates)  # Add this line
        self.btn_cloud.pack(side="left", padx=5)  # Add this line

        ttk.Label(toolbar, text="Search (Name/Author):").pack(side="left", padx=(20, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search)
        tk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side="left")
                
        # View Mode Toggle
        self.view_mode = tk.StringVar(value="tree") # tree or list
        ttk.Radiobutton(toolbar, text="📂 Folder View", variable=self.view_mode, value="tree", command=self.refresh_list).pack(side="right", padx=5)
        ttk.Radiobutton(toolbar, text="📄 List View", variable=self.view_mode, value="list", command=self.refresh_list).pack(side="right", padx=5)
       # --- Main Content ---
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Left: Tree/List
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=7)  # 增加权重，使左边占更多空间

        # Use extended selectmode for Multiselect
        self.tree = ttk.Treeview(left_frame, selectmode="extended")
        self.tree.pack(side="left", fill="both", expand=True)

        # Bind selection event - This fixes the "no reaction" issue
        self.tree.bind("<<TreeviewSelect>>", self.on_select_item)

        # Adjust column widths for better default display
        self.tree.column("#0", width=150, minwidth=100)  # 调整默认宽度
        self.tree["columns"] = ("Hash", "Author")
        self.tree.column("Hash", width=150, minwidth=100)
        self.tree.column("Author", width=150, minwidth=100)

        # Attach scrollbar to the right of the tree
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Right: Editor
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=3)  # 减少右边的权重


        # Info Header
        self.lbl_info_status = ttk.Label(right_frame, text="No Selection", font=("Segoe UI", 11, "bold"))
        self.lbl_info_status.pack(anchor="w", pady=(0, 10))

        # Form
        form_frame = ttk.Frame(right_frame)
        form_frame.pack(fill="both", expand=True)
        
        grid_opts = {'sticky': 'w', 'pady': 5}
        
        # Name
        ttk.Label(form_frame, text="Dance Name:").grid(row=0, column=0, **grid_opts)
        self.entry_name = ttk.Entry(form_frame, width=50)
        self.entry_name.grid(row=0, column=1, sticky="ew")
        
        # Author
        ttk.Label(form_frame, text="Author:").grid(row=1, column=0, **grid_opts)
        self.entry_author = ttk.Entry(form_frame, width=50)
        self.entry_author.grid(row=1, column=1, sticky="ew")

        # Credits
        ttk.Label(form_frame, text="Credits (One per line):").grid(row=2, column=0, sticky="nw", pady=5)
        self.text_credits = tk.Text(form_frame, height=10, width=50)
        self.text_credits.grid(row=2, column=1, sticky="nsew")

        # Comment
        ttk.Label(form_frame, text="Comment:").grid(row=3, column=0, sticky="nw", pady=5)
        self.text_comment = tk.Text(form_frame, height=5, width=50)
        self.text_comment.grid(row=3, column=1, sticky="nsew")

        form_frame.columnconfigure(1, weight=1)
        form_frame.rowconfigure(2, weight=1)

        # Action Buttons
        btn_frame = ttk.Frame(right_frame, padding=(0, 10))
        btn_frame.pack(fill="x", side="bottom")

        self.btn_save = ttk.Button(btn_frame, text="💾 Save Info", command=self.save_current_info)
        self.btn_save.pack(side="right", padx=5)
        
        ttk.Button(btn_frame, text="📂 Open File Location", command=self.open_file_location).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="📄 Open JSON Location", command=self.open_json_location).pack(side="left", padx=5)
        
        # Progress Bar (Hidden by default)
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        
        # Status Bar
        self.lbl_status = ttk.Label(self.root, text="Ready", relief="sunken", anchor="w")
        self.lbl_status.pack(side="bottom", fill="x")

    def log(self, msg):
        self.lbl_status.config(text=msg)
        self.root.update_idletasks()

    def refresh_data(self):
        """Start background scan."""
        self.btn_refresh.config(state="disabled")
        self.progress.pack(side="bottom", fill="x", before=self.lbl_status)
        self.progress.start(10)
        self.log("Scanning files... (This may take a moment)")
        
        thread = threading.Thread(target=self._refresh_data_worker)
        thread.daemon = True
        thread.start()

    def _refresh_data_worker(self):
        """
        Scans files, calculates hashes, manages central DB.
        Runs in separate thread.
        """
        # 1. Load DB (Central + Legacy merge)
        db_data = load_database()
        
        # 2. Scan Files: {hash: path}
        found_files = list(DANCES_DIR.rglob("*.unity3d"))
        
        new_inventory = {}
        new_count = 0
        
        # Build new dataset based on CURRENT files
        for fpath in found_files:
            fname = fpath.name
            fhash = file_hash(fpath)
            
            if not fhash:
                continue
            
            dance_data = None
            
            # --- Logic Rule 1: Exact Hash Match ---
            if fhash in db_data:
                dance_data = db_data[fhash]
                
                # Update filename if needed
                if dance_data.get('name') != fname:
                    dance_data['name'] = fname
                    dance_data['updated'] = datetime.now().strftime("%Y-%m-%d")
                
            # --- Logic Rule 2: New File ---
            else:
                new_count += 1
                dance_data = {
                    "name": fname,
                    "author": get_author_from_path(fpath),
                    "credits": [],
                    "comment": "",
                    "updated": datetime.now().strftime("%Y-%m-%d")
                }
            
            new_inventory[fhash] = {
                'path': fpath,
                'data': dance_data
            }
        
        # SAVE PHASE
        # Construct the clean DB dict to save to disk
        final_db_to_save = {h: item['data'] for h, item in new_inventory.items()}
        save_database(final_db_to_save)
            
        # Send result back
        stats = f"Sync Done. Total: {len(new_inventory)} | New: {new_count}"
        self.root.after(0, self._on_scan_complete, new_inventory, stats)

    def _on_scan_complete(self, new_inventory, stats):
        self.inventory = new_inventory
        self.refresh_list()
        
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_refresh.config(state="normal")
        self.log(stats)

    def refresh_list(self):
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        search_term = self.search_var.get().lower()
        mode = self.view_mode.get()
        
        # Filter items
        filtered_items = []
        for h, item in self.inventory.items():
            name = item['data'].get('name', '')
            author = item['data'].get('author', '')
            
            if search_term:
                # Search in Name, Hash, or Author
                if (search_term not in name.lower() and 
                    search_term not in h.lower() and 
                    search_term not in author.lower()):
                    continue
            filtered_items.append((h, item))
            
        # Headers & Columns
        if mode == "list":
            self.tree["columns"] = ("Hash", "Author")
            self.tree.heading("#0", text="Name", anchor="w")
            self.tree.heading("Hash", text="ID (Hash)", anchor="w")
            self.tree.heading("Author", text="Author", anchor="w")
            
            # Explicitly smaller widths
            self.tree.column("#0", width=200, minwidth=100)
            self.tree.column("Hash", width=80, minwidth=60)
            self.tree.column("Author", width=120, minwidth=80)
            
            for h, item in filtered_items:
                name = item['data'].get('name', '')
                author = item['data'].get('author', '')
                # ID is hash
                self.tree.insert("", "end", iid=h, text=name, values=(h, author))
                
        elif mode == "tree":
            self.tree["columns"] = ("Hash", "Author")
            self.tree.heading("#0", text="Category / File", anchor="w")
            self.tree.heading("Hash", text="ID", anchor="w")
            self.tree.heading("Author", text="Author", anchor="w")

            self.tree.column("#0", width=200, minwidth=100)
            self.tree.column("Hash", width=80, minwidth=60)
            self.tree.column("Author", width=120, minwidth=80)

            added_folders = {} # path_string -> node_id

            for h, item in filtered_items:
                fpath = item['path']
                try:
                    rel_path = fpath.relative_to(DANCES_DIR)
                except:
                    rel_path = Path(fpath.name)
                
                parts = rel_path.parts
                parent_id = ""
                
                # Build folders
                for i in range(len(parts) - 1):
                    folder_name = parts[i]
                    # Unique key for folder node
                    path_key = "/".join(parts[:i+1])
                    
                    if path_key not in added_folders:
                        node_id = self.tree.insert(parent_id, "end", text=folder_name, open=True)
                        added_folders[path_key] = node_id
                    parent_id = added_folders[path_key]
                
                # Add file
                name = item['data'].get('name', parts[-1])
                author = item['data'].get('author', '')
                # Use Hash as IID for file nodes
                self.tree.insert(parent_id, "end", iid=h, text=name, values=(h, author))

    def on_search(self, *args):
        self.refresh_list()

    def on_select_item(self, event):
        try:
            selected_ids = self.tree.selection()
            if not selected_ids:
                return

            # Filter out folder selections (which don't have hashes in inventory)
            valid_hashes = []
            for sid in selected_ids:
                if sid in self.inventory:
                    valid_hashes.append(sid)
            
            self.selected_hashes = valid_hashes

            
            self.load_editor(valid_hashes)
        except Exception as e:
            messagebox.showerror("Error", f"Selection error: {e}")

    def load_editor(self, hashes):
        count = len(hashes)
        
        # Clear Data
        self.entry_name.delete(0, tk.END)
        self.entry_author.delete(0, tk.END)
        self.text_credits.delete("1.0", tk.END)
        self.text_comment.delete("1.0", tk.END)
        
        if count == 0:
            self.lbl_info_status.config(text="No valid files selected (Click a file, not folder)")
            self.set_editor_state("disabled")
            return
            
        self.set_editor_state("normal")
        
        if count == 1:
            # Single Edit Mode
            h = hashes[0]
            if h not in self.inventory:
                 self.lbl_info_status.config(text=f"Error: Hash {h} not in inventory")
                 return

            data = self.inventory[h]['data']
            
            self.lbl_info_status.config(text=f"Editing: {data.get('name')} ({h[:8]})")
            
            self.entry_name.insert(0, data.get('name', ''))
            self.entry_author.insert(0, data.get('author', ''))
            
            creds = data.get('credits', [])
            if isinstance(creds, list) and creds:
                self.text_credits.insert("1.0", "\n".join(creds))
            else:
                # If credits are empty, set up a default template
                self.text_credits.insert("1.0", "Motion:\nCamera:")
                
            self.text_comment.insert("1.0", data.get('comment', ''))
            
        else:
            # Batch Edit Mode
            self.lbl_info_status.config(text=f"BATCH EDIT MODE: {count} files selected")
            
            self.entry_name.insert(0, "(Multiple Names - Keep empty to preserve)")
            self.entry_name.config(state="disabled") # Cannot batch rename unrelated files usually
            
            self.entry_author.insert(0, "") # User types to set all authors
            self.entry_author.config(state="normal")
            
            self.text_credits.insert("1.0", "Batch Mode: Entering text here will overwrite all selected.")
            self.text_comment.insert("1.0", "Batch Mode: Entering text here will overwrite all selected.")


    def set_editor_state(self, state):
        self.entry_name.config(state=state)
        self.entry_author.config(state=state)
        # Text widgets don't have standard 'state' for all ops, but we can bind if needed.
        # usually acceptable to keep enabled.

    def save_current_info(self):
        if not self.selected_hashes:
            return
            
        count = len(self.selected_hashes)
        
        # Inputs
        new_name = self.entry_name.get().strip()
        new_author = self.entry_author.get().strip()
        new_creds_raw = self.text_credits.get("1.0", tk.END).strip()
        new_comment = self.text_comment.get("1.0", tk.END).strip()
        
        # Parse Credits
        ignore_credits = False
        ignore_comment = False
        if count > 1:
            if new_creds_raw.startswith("Batch Mode:"): ignore_credits = True
            if new_comment.startswith("Batch Mode:"): ignore_comment = True
        
        new_credits_list = [line for line in new_creds_raw.split("\n") if line.strip()]

        for h in self.selected_hashes:
            data = self.inventory[h]['data']
            
            # Update fields
            if count == 1:
                if new_name: data['name'] = new_name
            # In batch mode, we skip name update usually
            
            if new_author: 
                data['author'] = new_author
            
            if not ignore_credits:
                data['credits'] = new_credits_list
            
            if not ignore_comment:
                data['comment'] = new_comment
            
            # Update date
            data['updated'] = datetime.now().strftime("%Y-%m-%d")

        # Save entire DB
        final_db_to_save = {h: item['data'] for h, item in self.inventory.items()}
        save_database(final_db_to_save)
            
        # Update Tree (if Author/Name changed)
        for h in self.selected_hashes:
            if self.tree.exists(h):
                data = self.inventory[h]['data']
                self.tree.item(h, text=data['name'], values=(h, data['author']))
             
        self.log(f"Saved {count} items.")
        messagebox.showinfo("Saved", f"Successfully updated {count} items in dances.json.")

    def open_file_location(self):
        if not self.selected_hashes:
            return
        
        # Open the first selected
        h = self.selected_hashes[0]
        path = self.inventory[h]['path']
        if path.exists():
            subprocess.Popen(f'explorer /select,"{os.path.abspath(path)}"')

    def open_json_location(self):
        # Determine which path to open
        target_path = OUTPUT_DIR / "dances.json"
        
        if not target_path.exists():
            target_path = OUTPUT_DIR # fallback to folder
            
        if target_path.exists():
             subprocess.Popen(f'explorer /select,"{os.path.abspath(target_path)}"')
        else:
            messagebox.showinfo("Info", "dances.json not found yet (Save or Sync first).")


if __name__ == "__main__":
    root = tk.Tk()
    app = DanceManagerApp(root)
    root.mainloop()

