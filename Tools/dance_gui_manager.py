import os
import json
import hashlib
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
DANCES_DIR = Path("./Dances")
OUTPUT_DIR = Path("./DanceStates/DanceInfo")
DANCE_INFO_DIR = OUTPUT_DIR / "dances"

# Map folder names to authors (can be extended)
AUTHOR_MAP = {
    "Dances": "JustAIter",
    "tanito": "tanito",
    "wdsa": "wdsa",
    "安卓喵": "安卓喵",
    "Xenophon": "Xenophon"
}

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
DANCE_INFO_DIR.mkdir(exist_ok=True, parents=True)
DANCES_JSON_PATH = OUTPUT_DIR / "dances.json"

# ---------------------------------------------------------
# BACKEND LOGIC
# ---------------------------------------------------------

def get_author_from_path(file_path: Path) -> str:
    """Guess author based on folder name."""
    parts = file_path.parts
    # Current file path might be relative or absolute. 
    # If relative to workspace: (Dances, Subfolder, file.unity3d)
    # We look for the folder directly inside 'Dances' or the parent folder.
    try:
        # relative_to throws if not relative, handle just in case
        rel = file_path.relative_to(DANCES_DIR)
        if len(rel.parts) > 1:
            folder_name = rel.parts[0]
            if folder_name in AUTHOR_MAP:
                return AUTHOR_MAP[folder_name]
    except ValueError:
        pass
    
    # Fallback: check parent name directly
    parent_name = file_path.parent.name
    return AUTHOR_MAP.get(parent_name, "Unknown")  # Default to Unknown or keep existing

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

def load_master_index():
    if DANCES_JSON_PATH.exists():
        try:
            with open(DANCES_JSON_PATH, "r", encoding="utf8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_master_index(data):
    with open(DANCES_JSON_PATH, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_dance_detail(hash_id):
    path = DANCE_INFO_DIR / f"{hash_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf8") as f:
                return json.load(f)
        except:
            return None
    return None

def save_dance_detail(hash_id, data):
    path = DANCE_INFO_DIR / f"{hash_id}.json"
    data["updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def delete_dance_detail(hash_id):
    path = DANCE_INFO_DIR / f"{hash_id}.json"
    if path.exists():
        os.remove(path)

# ---------------------------------------------------------
# GUI APPLICATION
# ---------------------------------------------------------

class DanceManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Custom Avatars: Borrowing Table Manager")
        self.root.geometry("1100x700")

        # Data
        self.master_index = {} # Content of dances.json
        self.unity_files_map = {} # path -> hash
        self.current_hash = None
        
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        # Style
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        # --- Toolbar ---
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(side="top", fill="x")
        
        ttk.Button(toolbar, text="Refresh & Sync (Scan Files)", command=self.refresh_data).pack(side="left", padx=5)
        ttk.Label(toolbar, text="Search:").pack(side="left", padx=(20, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search)
        tk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side="left")
        
        # View Mode Toggle
        self.view_mode = tk.StringVar(value="tree") # tree or list
        ttk.Radiobutton(toolbar, text="Folder View", variable=self.view_mode, value="tree", command=self.refresh_list).pack(side="right", padx=5)
        ttk.Radiobutton(toolbar, text="List View", variable=self.view_mode, value="list", command=self.refresh_list).pack(side="right", padx=5)

        # --- Main Content ---
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Left: List/Tree
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        self.tree = ttk.Treeview(left_frame, selectmode="browse")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_item)

        # Right: Editor
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=2) # Editor is wider

        # Info Header
        self.lbl_info_status = ttk.Label(right_frame, text="No Selection", font=("Segoe UI", 10, "bold"))
        self.lbl_info_status.pack(anchor="w", pady=(0, 10))

        # Form
        form_frame = ttk.Frame(right_frame)
        form_frame.pack(fill="both", expand=True)
        
        grid_opts = {'sticky': 'w', 'pady': 5}
        
        ttk.Label(form_frame, text="Dance Name:").grid(row=0, column=0, **grid_opts)
        self.entry_name = ttk.Entry(form_frame, width=50)
        self.entry_name.grid(row=0, column=1, sticky="ew")

        ttk.Label(form_frame, text="Author:").grid(row=1, column=0, **grid_opts)
        self.entry_author = ttk.Entry(form_frame, width=50)
        self.entry_author.grid(row=1, column=1, sticky="ew")

        ttk.Label(form_frame, text="Credits (One per line):").grid(row=2, column=0, sticky="nw", pady=5)
        self.text_credits = tk.Text(form_frame, height=10, width=50)
        self.text_credits.grid(row=2, column=1, sticky="nsew")

        ttk.Label(form_frame, text="Comment:").grid(row=3, column=0, sticky="nw", pady=5)
        self.text_comment = tk.Text(form_frame, height=5, width=50)
        self.text_comment.grid(row=3, column=1, sticky="nsew")

        form_frame.columnconfigure(1, weight=1)
        form_frame.rowconfigure(2, weight=1)

        # Action Buttons
        btn_frame = ttk.Frame(right_frame, padding=(0, 10))
        btn_frame.pack(fill="x", side="bottom")

        ttk.Button(btn_frame, text="Save Info", command=self.save_current_info).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Open File Location", command=self.open_file_location).pack(side="left", padx=5)
        
        self.lbl_status = ttk.Label(self.root, text="Ready", relief="sunken", anchor="w")
        self.lbl_status.pack(side="bottom", fill="x")

    def log(self, msg):
        self.lbl_status.config(text=msg)
        self.root.update_idletasks()

    def refresh_data(self):
        """Scans the file system and reconciles with JSON data."""
        self.log("Scanning files...")
        
        # 1. Load existing DB
        self.master_index = load_master_index()
        
        # 2. Scan Files
        found_files = list(DANCES_DIR.rglob("*.unity3d"))
        
        # Prepare for reconciliation
        # Create a reverse map of {filename: hash} from EXISTING DB to detect updates by name
        filename_to_hash = {v['name']: k for k, v in self.master_index.items()}
        
        processed_hashes = set()
        details_updated = 0
        migrated = 0
        new_added = 0
        
        # Temporary storage for new master index
        new_master_index = {}

        for fpath in found_files:
            fname = fpath.name
            
            # Calculate current hash
            curr_hash = file_hash(fpath)
            if not curr_hash:
                continue
                
            processed_hashes.add(curr_hash)
            
            # Logic:
            # Case A: Same Hash exists. Good.
            # Case B: Filename exists but Hash changed -> File Updated. Migrate data.
            # Case C: New File.
            
            final_hash_for_entry = curr_hash
            is_migrated = False
            
            # Check for migration (Name match, Hash mismatch)
            if fname in filename_to_hash:
                old_hash = filename_to_hash[fname]
                if old_hash != curr_hash:
                    # MIGRATION NEEDED
                    print(f"Migrating {fname}: {old_hash} -> {curr_hash}")
                    old_data = load_dance_detail(old_hash)
                    if old_data:
                        # Save old data to new hash file
                        # We keep the old data's credits/comments, but update name/hash
                        save_dance_detail(curr_hash, old_data)
                        # Optionally delete old JSON (safe to delete as it is superseded)
                        delete_dance_detail(old_hash)
                        is_migrated = True
                        migrated += 1
            
            # Determine Author
            # If we have existing data for this hash (either pre-existing or just migrated), use it
            # Otherwise guess from folder
            existing_detail = load_dance_detail(curr_hash)
            
            if existing_detail:
                # Ensure Name matches file name (in case of rename but same content)
                if existing_detail.get('name') != fname:
                    existing_detail['name'] = fname
                    save_dance_detail(curr_hash, existing_detail)
                    details_updated += 1
                
                display_author = existing_detail.get('author', get_author_from_path(fpath))
            else:
                # New Entry Creation
                guessed_author = get_author_from_path(fpath)
                new_entry = {
                    "name": fname,
                    "author": guessed_author,
                    "credits": [],
                    "comment": "",
                    "updated": datetime.now().strftime("%Y-%m-%d")
                }
                save_dance_detail(curr_hash, new_entry)
                new_added += 1
                display_author = guessed_author
            
            # Add to new master index
            new_master_index[curr_hash] = {
                "name": fname,
                "author": display_author,
                "credits": [], # Summary doesn't need full credits usually, but keeping struct
                "infoUrl": f"dances/{curr_hash}.json",
                "updated": datetime.now().strftime("%Y-%m-%d"),
                # Internal use mainly
                "_fullpath": str(fpath) 
            }

        # 3. Handle Deletions
        # Any hash in old master_index not in processed_hashes is essentially "Missing file"
        # We generally re-write the master_index to only include PRESENT files to keep it clean.
        # Clean up orphaned JSONs optionally? For now, we just reconstruct master_index.
        
        self.master_index = new_master_index
        save_master_index(self.master_index)
        
        self.log(f"Sync Complete. Added: {new_added}, Migrated: {migrated}, Total: {len(self.master_index)}")
        self.refresh_list()

    def refresh_list(self):
        # Clear Tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        search_term = self.search_var.get().lower()
        mode = self.view_mode.get()
        
        # Prepare items
        items_to_show = []
        for h, data in self.master_index.items():
            name = data['name']
            author = data['author']
            if search_term:
                if search_term not in name.lower() and search_term not in author.lower():
                    continue
            items_to_show.append((h, data))
            
        # Display
        if mode == "list":
            self.tree["columns"] = ("Author", "Hash")
            self.tree.heading("#0", text="Name", anchor="w")
            self.tree.heading("Author", text="Author", anchor="w")
            self.tree.heading("Hash", text="Hash", anchor="w")
            
            for h, data in items_to_show:
                self.tree.insert("", "end", iid=h, text=data['name'], values=(data['author'], h))
                
        elif mode == "tree":
            self.tree["columns"] = ("Author",)
            self.tree.heading("#0", text="File Structure", anchor="w")
            self.tree.heading("Author", text="Author", anchor="w")
            
            # Build directory tree structure
            # We use the _fullpath stored in master_index
            added_paths = {} # path -> item_id
            
            for h, data in items_to_show:
                full_path_str = data.get('_fullpath')
                if not full_path_str:
                    # Fallback if path missing (shouldn't happen after sync)
                    self.tree.insert("", "end", iid=h, text=data['name'], values=(data['author']))
                    continue

                path_obj = Path(full_path_str)
                try:
                    rel_path = path_obj.relative_to(DANCES_DIR)
                except ValueError:
                    rel_path = Path(path_obj.name) 

                parts = rel_path.parts
                parent_id = ""
                
                # Create folders
                for i in range(len(parts) - 1):
                    folder_name = parts[i]
                    path_key = "/".join(parts[:i+1])
                    if path_key not in added_paths:
                        # Add folder
                        # Folder ID can be just path_key
                        new_id = self.tree.insert(parent_id, "end", text=folder_name, open=True, image="") # could add folder icon
                        added_paths[path_key] = new_id
                    parent_id = added_paths[path_key]
                
                # Add file
                self.tree.insert(parent_id, "end", iid=h, text=parts[-1], values=(data['author'],))

    def on_search(self, *args):
        self.refresh_list()

    def on_select_item(self, event):
        selected = self.tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        
        # If it's a folder (doesn't exist in master_index), ignore
        if item_id not in self.master_index:
            return

        # Auto-save previous if needed (omitted for simplicity, but good practice)
        self.load_editor(item_id)

    def load_editor(self, hash_id):
        self.current_hash = hash_id
        detail = load_dance_detail(hash_id)
        
        if not detail:
            self.lbl_info_status.config(text=f"Error: No detail for {hash_id}")
            return

        self.lbl_info_status.config(text=f"Editing: {detail.get('name')}")
        
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, detail.get('name', ''))
        
        self.entry_author.delete(0, tk.END)
        self.entry_author.insert(0, detail.get('author', ''))
        
        self.text_credits.delete("1.0", tk.END)
        creds = detail.get('credits', [])
        if isinstance(creds, list):
            self.text_credits.insert("1.0", "\n".join(creds))
        else:
            self.text_credits.insert("1.0", str(creds))
            
        self.text_comment.delete("1.0", tk.END)
        self.text_comment.insert("1.0", detail.get('comment', ''))

    def save_current_info(self):
        if not self.current_hash:
            return
            
        # Gather data
        name = self.entry_name.get().strip()
        author = self.entry_author.get().strip()
        
        creds_raw = self.text_credits.get("1.0", tk.END).strip()
        credits_list = [line for line in creds_raw.split("\n") if line.strip()]
        
        comment = self.text_comment.get("1.0", tk.END).strip()
        
        # Load existing to preserve other fields
        data = load_dance_detail(self.current_hash) or {}
        
        data['name'] = name
        data['author'] = author
        data['credits'] = credits_list
        data['comment'] = comment
        
        save_dance_detail(self.current_hash, data)
        
        # Update master index in memory and file
        if self.current_hash in self.master_index:
            self.master_index[self.current_hash]['name'] = name
            self.master_index[self.current_hash]['author'] = author
            save_master_index(self.master_index)
            
        self.log(f"Saved info for {name}")
        
        # Refresh tree item label if name changed
        if self.tree.exists(self.current_hash):
            self.tree.item(self.current_hash, text=name, values=(author,))
            
    def open_file_location(self):
        if not self.current_hash or self.current_hash not in self.master_index:
            return
            
        path_str = self.master_index[self.current_hash].get('_fullpath')
        if path_str and os.path.exists(path_str):
            subprocess.Popen(f'explorer /select,"{os.path.abspath(path_str)}"')
        else:
            messagebox.showwarning("File Missing", "The file for this entry cannot be found.")

if __name__ == "__main__":
    root = tk.Tk()
    app = DanceManagerApp(root)
    root.mainloop()
