import os
import json
import hashlib
import threading
import tkinter as tk
import urllib.request
import urllib.error
import subprocess
import webbrowser
import time
import ssl
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox, filedialog, simpledialog

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

# The endpoint for uploading/syncing (User specific, implemented via Cloudflare Worker ideally)
UPLOAD_ENDPOINT = "https://dance-uploader.xenophn.workers.dev" 

CLOUD_URLS = [ 
    "https://unitydanceinfo.pages.dev/DanceInfo/dances.json",
    "https://maoxig.github.io/UnityDanceInfo/DanceInfo/dances.json"
]

# ---------------------------------------------------------
# BACKEND & LOGIC
# ---------------------------------------------------------

class DanceManagerBackend:
    def __init__(self):
        self.db_data = {}         # The Master Database {hash: metadata}
        self.inventory = {}       # Local Files {hash: path}
        
        # Path Configuration (Default to cwd)
        self.root_dir = Path(".").resolve()
        self.dances_dir = self.root_dir / "Dances"
        self.db_file = self.root_dir / "DanceStates" / "DanceInfo" / "dances.json"
        
        self.ensure_dirs()
    
    def set_root_path(self, path_str):
        """Update working directory and reload DB."""
        self.root_dir = Path(path_str).resolve()
        self.dances_dir = self.root_dir / "Dances"
        self.db_file = self.root_dir / "DanceStates" / "DanceInfo" / "dances.json"
        
        self.ensure_dirs()
        self.load_db()

    def ensure_dirs(self):
        try:
            self.db_file.parent.mkdir(parents=True, exist_ok=True)
        except:
            pass

    def load_db(self):
        """Load local JSON database."""
        if self.db_file.exists():
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    self.db_data = json.load(f)
            except Exception as e:
                print(f"Error loading DB: {e}")
                self.db_data = {}
        else:
            self.db_data = {}

    def save_db(self):
        """Save Master Database to JSON."""
        try:
            # OPTIMIZATION: Remove empty comments to save space
            for k in self.db_data:
                if 'comment' in self.db_data[k] and not self.db_data[k]['comment']:
                    del self.db_data[k]['comment']

            # Sort the dances by author, then by name, then by hash
            sorted_dances = dict(sorted(
                self.db_data.items(),
                key=lambda item: (item[1]['author'], item[1]['name'], item[0])
            ))

            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump(sorted_dances, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error saving DB: {e}")
            return False

    def scan_local_files(self):
        """
        Scans local files, hashes them, and updates the DB with new entries if found.
        Returns: (inventory_dict, new_files_count)
        """
        # Ensure dir exists before scanning
        if not self.dances_dir.exists():
            return {}, 0
            
        found_files = list(self.dances_dir.rglob("*.unity3d"))
        current_inventory = {}
        new_count = 0

        for fpath in found_files:
            # Calculate Hash
            fhash = self._compute_hash(fpath)
            if not fhash:
                continue

            # Update Inventory Mapping
            current_inventory[fhash] = fpath

            # Sync with DB
            if fhash not in self.db_data:
                # New file found locally that isn't in DB -> Add it
                new_count += 1
                self.db_data[fhash] = {
                    "name": fpath.stem, # Optimize: use stem (no .unity3d)
                    "author": self._guess_author(fpath),
                    "credits": [],
                    # Optimized: Don't init empty comment
                    "updated": datetime.now().strftime("%Y-%m-%d")
                }
            else:
                # Existing file. Ensure basic fields exist
                if "updated" not in self.db_data[fhash]:
                     self.db_data[fhash]["updated"] = datetime.now().strftime("%Y-%m-%d")

        self.inventory = current_inventory
        return self.inventory, new_count

    def fetch_cloud_db(self):
        """Fetch DB from cloud mirrors with improved stability."""
        ctx = ssl.create_default_context()
        # Fallback for some systems with old certs, though we try to stay secure
        try:
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
        except:
            pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DanceManager/1.0"
        }

        for url in CLOUD_URLS:
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                        if response.status == 200:
                            return json.loads(response.read().decode('utf-8'))
                except Exception as e:
                    print(f"Fetch failed for {url} (Attempt {attempt+1}): {e}")
                    time.sleep(1)
        return None

    def upload_to_cloud(self, username, upload_url):
        """
        Uploads the current local DB to a compatible worker/server.
        Expected Server Logic: Receive JSON {username, timestamp, content}, save to storage.
        """
        if not upload_url:
            return False, "Upload URL is not configured (See UPLOAD_ENDPOINT in code)."
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        payload = {
            "username": username,
            "timestamp": timestamp,
            "filename": "dances.json",
            "content": self.db_data
        }
        
        try:
            json_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(upload_url, data=json_bytes, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('User-Agent', 'DanceManager/1.0')
            
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                if 200 <= response.status < 300:
                    return True, "Upload successful!"
                else:
                    return False, f"Server returned status: {response.status}\n{response.read().decode()}"
        except Exception as e:
            return False, f"Upload error: {e}"

    def calculate_cloud_diffs(self, cloud_data):
        """
        Compare Cloud Data vs Local DB.
        Returns list of (hash, change_type)
        """
        diffs = []
        for h, c_item in cloud_data.items():
            if h in self.db_data:
                l_item = self.db_data[h]
                # Check for content differences
                # Convert to string for simple comparison or check fields
                if (str(c_item.get('name')) != str(l_item.get('name')) or
                    str(c_item.get('author')) != str(l_item.get('author')) or
                    c_item.get('credits') != l_item.get('credits') or
                    str(c_item.get('comment')) != str(l_item.get('comment'))):
                    diffs.append((h, "UPDATE"))
            else:
                # Completely new entry (User doesn't have it in DB)
                diffs.append((h, "NEW DB ENTRY"))
        return diffs

    def merge_cloud_item(self, h, cloud_item):
        """Merge a single cloud item into local DB."""
        self.db_data[h] = cloud_item
        self.db_data[h]['updated'] = datetime.now().strftime("%Y-%m-%d")

    def _compute_hash(self, path):
        h = hashlib.md5()
        try:
            with path.open("rb") as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            return h.hexdigest()[:8]
        except:
            return None

    def _guess_author(self, path):
        # Simply use parent folder name as author
        try:
            # Check if file is directly in Dances root or in subdir
            if path.parent.resolve() == self.dances_dir.resolve():
                return "Unknown"
            return path.parent.name
        except:
            return "Unknown"

# ---------------------------------------------------------
# DIALOGS
# ---------------------------------------------------------

class CloudSyncDialog(tk.Toplevel):
    def __init__(self, parent, local_db, cloud_db, on_apply):
        super().__init__(parent)
        self.title("Sync with Cloud")
        self.geometry("1000x600")
        self.transient(parent)
        self.grab_set()

        self.local_db = local_db
        self.cloud_db = cloud_db
        self.on_apply = on_apply
        
        # Calculate diffs
        self.backend = DanceManagerBackend() # Just for helper method access without instance state
        self.backend.db_data = local_db # Hacky context sharing
        self.diffs = self.backend.calculate_cloud_diffs(cloud_db)

        self.setup_ui()
        self.populate_list()

    def setup_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Left: List
        left_frame = ttk.Labelframe(paned, text="Differences")
        self.lb_diffs = tk.Listbox(left_frame, width=30)
        self.lb_diffs.pack(fill="both", expand=True, padx=5, pady=5)
        self.lb_diffs.bind("<<ListboxSelect>>", self.on_select)
        paned.add(left_frame, weight=1)

        # Right: Details
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self.comp_frame = ttk.Frame(right_frame)
        self.comp_frame.pack(fill="x", padx=10, pady=10)

        # Headers
        headers = ["Field", "Local DB", "Cloud DB"]
        for i, t in enumerate(headers):
            ttk.Label(self.comp_frame, text=t, font=("", 10, "bold")).grid(row=0, column=i, sticky="w", padx=5)

        # Fields
        self.widgets = {}
        fields = ["name", "author", "credits", "comment"]
        for idx, f in enumerate(fields, 1):
            ttk.Label(self.comp_frame, text=f.capitalize()).grid(row=idx, column=0, sticky="nw", pady=2)
            
            l_txt = tk.Text(self.comp_frame, height=3, width=35, bg="#f0f0f0", state="disabled")
            l_txt.grid(row=idx, column=1, sticky="w", padx=5)
            
            c_txt = tk.Text(self.comp_frame, height=3, width=35, bg="#e3f2fd", state="disabled")
            c_txt.grid(row=idx, column=2, sticky="w", padx=5)
            
            self.widgets[f] = (l_txt, c_txt)

        # Buttons
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill="x", pady=20, padx=10)
        
        ttk.Button(btn_frame, text="✅ Apply Cloud (Select)", command=self.apply_single).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="❌ Ignore (Local)", command=self.ignore_single).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Apply ALL Cloud Updates", command=self.apply_all).pack(side="right", padx=5)

    def populate_list(self):
        self.lb_diffs.delete(0, tk.END)
        if not self.diffs:
            self.lb_diffs.insert(0, "No differences found.")
            return
        
        for h, dtype in self.diffs:
            name = self.cloud_db[h].get("name", "Unknown")
            self.lb_diffs.insert(tk.END, f"[{dtype}] {name}")

    def on_select(self, event):
        sel = self.lb_diffs.curselection()
        if not sel: return
        
        # Check index bounds
        idx = sel[0]
        if idx >= len(self.diffs): return

        h, _ = self.diffs[idx]
        local = self.local_db.get(h, {})
        cloud = self.cloud_db.get(h, {})
        
        for f in ["name", "author", "credits", "comment"]:
            l_val = self._fmt(local.get(f, ""))
            c_val = self._fmt(cloud.get(f, ""))
            
            self._set_txt(self.widgets[f][0], l_val)
            self._set_txt(self.widgets[f][1], c_val)

    def _fmt(self, val):
        if isinstance(val, list): return "\n".join(val)
        return str(val)

    def _set_txt(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def apply_single(self):
        sel = self.lb_diffs.curselection()
        if not sel: return
        idx = sel[0]
        # Check index bounds
        if idx >= len(self.diffs): return

        h, _ = self.diffs[idx]
        
        self.on_apply(h, self.cloud_db[h])
        
        del self.diffs[idx]
        self.populate_list()
        
        if self.diffs:
            self.lb_diffs.selection_set(0)
            self.on_select(None)
        else:
            messagebox.showinfo("Finished", "All resolved.")
            self.destroy()

    def ignore_single(self):
        sel = self.lb_diffs.curselection()
        if not sel: return
        # Check index bounds
        idx = sel[0]
        if idx >= len(self.diffs): return

        del self.diffs[idx]
        self.populate_list()

    def apply_all(self):
        if not messagebox.askyesno("Confirm", "Overwrite ALL local DB entries with Cloud data?"):
            return
        for h, _ in self.diffs:
            self.on_apply(h, self.cloud_db[h])
        self.diffs = []
        self.populate_list()
        messagebox.showinfo("Done", "All applied.")
        self.destroy()


# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------

class DanceManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dance Manager - Local Editor & Sync")
        self.root.geometry("1200x800")
        
        self.backend = DanceManagerBackend()
        self.selected_hashes = []
        
        self.setup_ui()
        
        # Initial Load
        self.log("Initializing...")
        self.root.after(200, self.run_startup_tasks)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=24)
        
        # --- Root Path Selector ---
        path_frame = ttk.Frame(self.root, padding=5)
        path_frame.pack(fill="x")
        
        ttk.Label(path_frame, text="Mod Folder:").pack(side="left")
        
        self.var_root_path = tk.StringVar(value=str(self.backend.root_dir))
        self.ent_path = ttk.Entry(path_frame, textvariable=self.var_root_path)
        self.ent_path.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_path.bind("<Return>", self.on_path_change)
        
        ttk.Button(path_frame, text="Browse", command=self.browse_root).pack(side="left")

        # --- Toolbar ---
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill="x")
        
        self.btn_refresh = ttk.Button(toolbar, text="🔄 Refresh Scan", command=self.refresh_scan)
        self.btn_refresh.pack(side="left", padx=2)
        
        self.btn_cloud = ttk.Button(toolbar, text="☁ Check Cloud", command=self.manual_cloud_check)
        self.btn_cloud.pack(side="left", padx=2)

        ttk.Button(toolbar, text="🌐 Visit Site", command=lambda: webbrowser.open(CLOUD_URLS[0])).pack(side="left", padx=2)
        ttk.Button(toolbar, text="⬆ Upload", command=self.on_upload_click).pack(side="left", padx=2)
        
        ttk.Label(toolbar, text="Search(Name/Author):").pack(side="left", padx=(15, 5))
        self.var_search = tk.StringVar()
        self.var_search.trace("w", self.on_search)
        ttk.Entry(toolbar, textvariable=self.var_search, width=25).pack(side="left")
        
        self.var_view = tk.StringVar(value="tree")
        ttk.Radiobutton(toolbar, text="Tree View", variable=self.var_view, value="tree", command=self.refresh_list).pack(side="right", padx=5)
        ttk.Radiobutton(toolbar, text="List View", variable=self.var_view, value="list", command=self.refresh_list).pack(side="right", padx=5)
        
        # --- Main Split ---
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Left: Inventory
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)
        
        self.tree = ttk.Treeview(left_frame, columns=("Hash", "Author"), selectmode="extended")
        self.tree.heading("#0", text="File / Name")
        self.tree.heading("Hash", text="MD5")
        self.tree.heading("Author", text="Author")
        self.tree.column("#0", width=250)
        self.tree.column("Hash", width=80)
        self.tree.column("Author", width=100)
        
        scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        # Right: Editor
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        
        self.setup_summary(right_frame)
        self.setup_editor(right_frame)
        
        # Status
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.lbl_status = ttk.Label(self.root, text="Ready", relief="sunken", anchor="w")
        self.lbl_status.pack(side="bottom", fill="x")

    def setup_summary(self, parent):
        frame = ttk.Labelframe(parent, text="Overview", padding=10)
        frame.pack(fill="x", padx=5, pady=5)
        
        self.lbl_summary_total = ttk.Label(frame, text="Total Dances: 0")
        self.lbl_summary_total.pack(anchor="w")
        
        self.lbl_summary_authors = ttk.Label(frame, text="Total Authors: 0")
        self.lbl_summary_authors.pack(anchor="w")

    def update_summary(self):
        total = len(self.backend.db_data)
        authors = set()
        for v in self.backend.db_data.values():
            if v.get('author'):
                authors.add(v['author'])
        
        self.lbl_summary_total.config(text=f"Total Dances: {total}")
        self.lbl_summary_authors.config(text=f"Total Authors: {len(authors)}")

    def setup_editor(self, parent):
        frame = ttk.Labelframe(parent, text="Item Details", padding=10)
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.lbl_editor_info = ttk.Label(frame, text="No Selection", font=("", 10, "italic"))
        self.lbl_editor_info.pack(anchor="w", pady=(0, 10))
        
        # Fields
        grid_kws = {'sticky': 'w', 'pady': 2}
        
        ttk.Label(frame, text="Name:").pack(anchor="w")
        self.ent_name = ttk.Entry(frame)
        self.ent_name.pack(fill="x", pady=(0, 5))
        
        ttk.Label(frame, text="Author:").pack(anchor="w")
        self.ent_author = ttk.Entry(frame)
        self.ent_author.pack(fill="x", pady=(0, 5))
        
        ttk.Label(frame, text="Credits (Lines):").pack(anchor="w")
        self.txt_credits = tk.Text(frame, height=6)
        self.txt_credits.pack(fill="x", pady=(0, 5))
        
        # Configure tag for placeholder/template
        self.txt_credits.tag_configure("template", foreground="#888888", font=("", 9, "italic"))
        # Bind to remove style on any key press
        self.txt_credits.bind("<KeyPress>", lambda e: self.txt_credits.tag_remove("template", "1.0", "end"))
        
        ttk.Label(frame, text="Comment:").pack(anchor="w")
        self.txt_comment = tk.Text(frame, height=4)
        self.txt_comment.pack(fill="x", pady=(0, 5))
        
        # Controls
        btn_box = ttk.Frame(frame)
        btn_box.pack(fill="x", pady=10)
        
        ttk.Button(btn_box, text="💾 Save Changes", command=self.save_local_changes).pack(side="right")
        ttk.Button(btn_box, text="📂 File Folder", command=self.open_file_folder).pack(side="left")
        ttk.Button(btn_box, text="📄 Json File", command=self.open_json_folder).pack(side="left", padx=5)

    def log(self, msg):
        self.lbl_status.config(text=msg)
        self.root.update_idletasks()

    # --- Logic ---

    def browse_root(self):
        path = filedialog.askdirectory(initialdir=self.var_root_path.get())
        if path:
            self.on_path_change(path_str=path)

    def on_path_change(self, event=None, path_str=None):
        if path_str:
            new_path = path_str
        else:
            new_path = self.var_root_path.get()
            
        self.var_root_path.set(new_path)
        self.backend.set_root_path(new_path)
        self.refresh_scan()

    def run_startup_tasks(self):
        # 1. Load DB
        self.backend.load_db()
        # 2. Scan Local
        self.refresh_scan()
        # 3. Check Cloud (Async)
        self.root.after(1000, lambda: self.run_cloud_check(silent=True))

    def refresh_scan(self):
        self.btn_refresh.config(state="disabled")
        self.progress.pack(side="bottom", fill="x", before=self.lbl_status)
        self.progress.start()
        self.log(f"Scanning local files in {self.backend.dances_dir}...")
        
        def worker():
            inv, new_cnt = self.backend.scan_local_files()
            self.root.after(0, self._on_scan_done, inv, new_cnt)
            
        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, inventory, new_count):
        print(f"DEBUG: Scan complete. Inventory: {len(inventory)}, New: {new_count}")
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_refresh.config(state="normal")
        
        # Save implicitly if new entries created
        if new_count > 0:
            self.backend.save_db()
            self.log(f"Scan complete. Added {new_count} new entries to DB.")
        else:
            self.log(f"Scan complete. {len(inventory)} local files.")
            
        self.refresh_list()

    def run_cloud_check(self, silent=False):
        if not silent:
            self.btn_cloud.config(state="disabled", text="Checking...")
        
        def worker():
            data = self.backend.fetch_cloud_db()
            self.root.after(0, self._on_cloud_result, data, silent)
        
        threading.Thread(target=worker, daemon=True).start()

    def _on_cloud_result(self, cloud_data, silent):
        self.btn_cloud.config(state="normal", text="☁ Check Cloud")
        
        if not cloud_data:
            if not silent: messagebox.showerror("Error", "Could not fetch cloud data.")
            return

        diffs = self.backend.calculate_cloud_diffs(cloud_data)
        count = len(diffs)
        
        if count > 0:
            self.btn_cloud.config(text=f"☁ Updates ({count})")
            if not silent:
                if messagebox.askyesno("Updates Found", f"Found {count} cloud updates. Review them?"):
                    self.open_sync_dialog(cloud_data)
        else:
            if not silent: messagebox.showinfo("Up to Date", "Local DB is in sync with Cloud.")

    def manual_cloud_check(self):
        self.run_cloud_check(silent=False)

    def open_sync_dialog(self, cloud_data):
        CloudSyncDialog(self.root, self.backend.db_data, cloud_data, self.apply_cloud_merge)

    def apply_cloud_merge(self, h, cloud_item):
        self.backend.merge_cloud_item(h, cloud_item)
        self.backend.save_db()
        self.refresh_list() # Refresh list to show new names

    def on_upload_click(self):
        username = simpledialog.askstring("Upload", "Enter your Contributor Name (Alpha-Numeric only):")
        if not username: return
        
        # Basic validation
        username = "".join(x for x in username if x.isalnum() or x in ('-', '_'))
        
        if not UPLOAD_ENDPOINT:
             if messagebox.askyesno("Setup", "Upload endpoint is not set. Would you like to open the configuration in browser?"):
                 webbrowser.open("https://unitydanceinfo.pages.dev") 
             return

        self.btn_cloud.config(state="disabled") # Quick disable
        self.log(f"Uploading as {username}...")
        
        def _worker():
            success, msg = self.backend.upload_to_cloud(username, UPLOAD_ENDPOINT)
            self.root.after(0, lambda: self._on_upload_done(success, msg))
            
        threading.Thread(target=_worker, daemon=True).start()

    def _on_upload_done(self, success, msg):
        self.btn_cloud.config(state="normal")
        self.log("Ready")
        
        if success:
            messagebox.showinfo("Success", "Upload Complete!\nThank you for contributing.")
        else:
            messagebox.showerror("Upload Failed", f"Error: {msg}")

    # --- UI Logic ---

    def refresh_list(self):
        self.update_summary()
        # Save selection
        sel = self.selected_hashes
        
        self.tree.delete(*self.tree.get_children())
        
        search = self.var_search.get().lower()
        mode = self.var_view.get()
        
        items = []
        for h, fpath in self.backend.inventory.items():
            meta = self.backend.db_data.get(h, {})
            # Use stem as fallback if name missing, to avoid extensions in display
            name = meta.get("name", fpath.stem)
            auth = meta.get("author", "Unknown")
            
            if search:
                if search not in name.lower() and search not in auth.lower() and search not in h.lower():
                    continue
            items.append((h, name, auth, fpath))
            
        if mode == "list":
            for h, name, auth, _ in items:
                self.tree.insert("", "end", iid=h, text=name, values=(h, auth))
        else:
            # Tree Mode (Folder structure)
            dirs = {}
            for h, name, auth, fpath in items:
                try:
                    rel = fpath.relative_to(self.backend.dances_dir)
                except:
                    # Fallback if path is somehow distinct or resolving err
                    rel = Path(fpath.name)
                
                parts = rel.parts
                parent = ""
                for i in range(len(parts) - 1):
                    p_key = "/".join(parts[:i+1])
                    if p_key not in dirs:
                        dirs[p_key] = self.tree.insert(parent, "end", text=parts[i], open=True)
                    parent = dirs[p_key]
                
                self.tree.insert(parent, "end", iid=h, text=name, values=(h, auth))
        
        # Restore selection if possible
        to_sel = [x for x in sel if self.tree.exists(x)]
        if to_sel:
            self.tree.selection_set(to_sel)

    def on_search(self, *args):
        self.refresh_list()

    def on_select(self, event):
        sel = self.tree.selection()
        
        # Filter only hash items (not folders)
        valid = [x for x in sel if x in self.backend.db_data]
        self.selected_hashes = valid
        
        self.populate_editor()

    def populate_editor(self):
        count = len(self.selected_hashes)
        
        self.ent_name.delete(0, tk.END)
        self.ent_author.delete(0, tk.END)
        self.txt_credits.delete("1.0", tk.END)
        self.txt_comment.delete("1.0", tk.END)
        
        if count == 0:
            self.lbl_editor_info.config(text="No valid file selected.")
            self.ent_name.config(state="normal") # Reset state in case it was disabled
            return
            
        if count == 1:
            h = self.selected_hashes[0]
            data = self.backend.db_data[h]
            
            raw_name = data.get('name', '')
            # Strip extension for editing convenience if present in old data
            if raw_name.lower().endswith('.unity3d'):
                raw_name = raw_name[:-8]

            self.lbl_editor_info.config(text=f"Editing: {data.get('name')} ({h})")
            self.ent_name.insert(0, raw_name)
            self.ent_author.insert(0, data.get('author', ''))
            
            cr = data.get('credits', [])
            if isinstance(cr, list) and cr:
                self.txt_credits.insert("1.0", "\n".join(cr))
            else:
                # Empty credits -> Show template
                self.txt_credits.insert("1.0", "Motion:\nCamera:", "template")
            
            self.txt_comment.insert("1.0", data.get('comment', ''))
            
            self.ent_name.config(state="normal")
        else:
            self.lbl_editor_info.config(text=f"Batch Editing {count} items")
            self.ent_name.insert(0, "(Multiple)")
            self.ent_name.config(state="disabled")
            self.ent_author.insert(0, "") # User types to overwrite
            self.txt_credits.insert("1.0", "Batch: Type to overwrite all.")
            self.txt_comment.insert("1.0", "Batch: Type to overwrite all.")

    def save_local_changes(self):
        if not self.selected_hashes: return
        
        hashes = self.selected_hashes
        is_batch = len(hashes) > 1
        
        new_name = self.ent_name.get().strip()
        # Save Name without extension to save space
        if new_name.lower().endswith('.unity3d'):
             new_name = new_name[:-8]

        new_auth = self.ent_author.get().strip()
        new_cred = self.txt_credits.get("1.0", "end-1c").strip().split("\n")
        new_comm = self.txt_comment.get("1.0", "end-1c").strip()
        
        # Batch checks
        skip_cred = is_batch and "Batch:" in new_cred[0]
        skip_comm = is_batch and "Batch:" in new_comm
        
        for h in hashes:
            data = self.backend.db_data[h]
            has_changed = False
            
            if not is_batch:
                if data.get('name') != new_name:
                    data['name'] = new_name
                    has_changed = True
            
            if new_auth and data.get('author') != new_auth: 
                data['author'] = new_auth
                has_changed = True

            if not skip_cred: 
                clean_cred = [x for x in new_cred if x]
                if data.get('credits') != clean_cred:
                    data['credits'] = clean_cred
                    has_changed = True
            
            # Optimized comment storage: Don't save empty string
            if not skip_comm: 
                current_comm = data.get('comment', '')
                if new_comm != current_comm:
                    if new_comm:
                        data['comment'] = new_comm
                    else:
                        data.pop('comment', None)
                    has_changed = True
            
            if has_changed:
                data['updated'] = datetime.now().strftime("%Y-%m-%d")
            
        self.backend.save_db()
        self.refresh_list()
        messagebox.showinfo("Saved", f"Updated {len(hashes)} items.")

    def open_file_folder(self):
        if not self.selected_hashes: return
        h = self.selected_hashes[0]
        path = self.backend.inventory.get(h)
        if path and path.exists():
            subprocess.Popen(f'explorer /select,"{path.resolve()}"')

    def open_json_folder(self):
        if self.backend.db_file.exists():
            subprocess.Popen(f'explorer /select,"{self.backend.db_file.resolve()}"')

if __name__ == "__main__":
    root = tk.Tk()
    app = DanceManagerApp(root)
    root.mainloop()
