# MTS_APP.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from MTS_world import get_and_convert_blocks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class BlockTextureUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Minecraft to Source Converter")
        self.window.geometry("900x600")

        # Default paths
        self.world_path = tk.StringVar(value=r"Localization to your Minecraft WORLD")
        self.output_path = tk.StringVar(value=r"Location to where you want to save the VMF file")

        # Selection coords
        self.x1 = tk.StringVar(value="-65")
        self.z1 = tk.StringVar(value="-65")
        self.x2 = tk.StringVar(value="65")
        self.z2 = tk.StringVar(value="65")

        # NEW: Y scan range
        self.y_min = tk.StringVar(value="-64")
        self.y_max = tk.StringVar(value="319")

        # NEW: excluded blocks (comma-separated)
        self.excluded_blocks = tk.StringVar(value="air,barrier,water,lava,grass,tall_grass,leaves")

        # Mirror settings
        self.mirror_axis = tk.StringVar(value="x")

        # Options
        self.optimize_var = tk.BooleanVar(value=False)
        self.center_var = tk.BooleanVar(value=True)

        self.setup_ui()

    def setup_ui(self):
        # Paths
        path_frame = ttk.LabelFrame(self.window, text="Paths", padding="5")
        path_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(path_frame, text="Minecraft World:").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.world_path, width=100).grid(row=0, column=1, padx=5)
        ttk.Button(path_frame, text="Browse", command=self.browse_world).grid(row=0, column=2)

        ttk.Label(path_frame, text="VMF Output:").grid(row=1, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.output_path, width=100).grid(row=1, column=1, padx=5)
        ttk.Button(path_frame, text="Browse", command=self.browse_output).grid(row=1, column=2)

        # Coordinates
        coord_frame = ttk.LabelFrame(self.window, text="Coordinates (X/Z)", padding="5")
        coord_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(coord_frame, text="X1:").grid(row=0, column=0)
        ttk.Entry(coord_frame, textvariable=self.x1, width=10).grid(row=0, column=1)

        ttk.Label(coord_frame, text="Z1:").grid(row=0, column=2)
        ttk.Entry(coord_frame, textvariable=self.z1, width=10).grid(row=0, column=3)

        ttk.Label(coord_frame, text="X2:").grid(row=1, column=0)
        ttk.Entry(coord_frame, textvariable=self.x2, width=10).grid(row=1, column=1)

        ttk.Label(coord_frame, text="Z2:").grid(row=1, column=2)
        ttk.Entry(coord_frame, textvariable=self.z2, width=10).grid(row=1, column=3)

        # Y range
        y_frame = ttk.LabelFrame(self.window, text="Y Scan Range", padding="5")
        y_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(y_frame, text="Y Min:").grid(row=0, column=0)
        ttk.Entry(y_frame, textvariable=self.y_min, width=10).grid(row=0, column=1)

        ttk.Label(y_frame, text="Y Max:").grid(row=0, column=2)
        ttk.Entry(y_frame, textvariable=self.y_max, width=10).grid(row=0, column=3)

        # Excluded blocks
        exclude_frame = ttk.LabelFrame(self.window, text="Excluded Blocks (comma-separated)", padding="5")
        exclude_frame.pack(fill="x", padx=5, pady=5)
        ttk.Entry(exclude_frame, textvariable=self.excluded_blocks, width=110).pack(fill="x")

        # Mirror + options
        options_frame = ttk.LabelFrame(self.window, text="Options", padding="5")
        options_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(options_frame, text="Mirror Axis (x/y):").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options_frame, textvariable=self.mirror_axis, values=["x", "y"], width=5).grid(row=0, column=1, padx=5)

        ttk.Checkbutton(options_frame, text="Optimize (merge blocks)", variable=self.optimize_var).grid(row=0, column=2, padx=10, sticky="w")
        ttk.Checkbutton(options_frame, text="Center map at origin", variable=self.center_var).grid(row=0, column=3, padx=10, sticky="w")

        # Convert button
        ttk.Button(self.window, text="Convert", command=self.convert).pack(pady=12)

        # Credits
        credit_frame = tk.Frame(self.window)
        credit_frame.pack(side="bottom", pady=5)

        credit_label = tk.Label(credit_frame, text="Original made by ", fg="black")
        credit_label.pack(side="left")

        daxen_link = tk.Label(credit_frame, text="Daxen", fg="blue", cursor="hand2")
        daxen_link.pack(side="left")
        daxen_link.bind("<Button-1>", lambda e: self.open_link("https://www.youtube.com/@iDaxen"))

        credit_label2 = tk.Label(credit_frame, text=" | Fixed & improved by ", fg="black")
        credit_label2.pack(side="left")

        lemon_link = tk.Label(credit_frame, text="LemoN", fg="goldenrod3", cursor="hand2")
        lemon_link.pack(side="left")
        lemon_link.bind("<Button-1>", lambda e: self.open_link("https://www.twitch.tv/lemonstreamuje"))

    def open_link(self, url):
        import webbrowser
        webbrowser.open_new(url)

    def run(self):
        self.window.mainloop()

    def browse_world(self):
        path = filedialog.askdirectory(title="Select Minecraft World Folder")
        if path:
            self.world_path.set(path)

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".vmf",
            filetypes=[("Valve Map File", "*.vmf")],
            title="Save VMF File As"
        )
        if path:
            self.output_path.set(path)

    def convert(self):
        try:
            excluded = [b.strip() for b in self.excluded_blocks.get().split(",") if b.strip()]

            get_and_convert_blocks(
                self.world_path.get(),
                int(self.x1.get()), int(self.z1.get()),
                int(self.x2.get()), int(self.z2.get()),
                self.output_path.get(),
                mirror_axis=self.mirror_axis.get(),
                optimize=self.optimize_var.get(),
                y_min=int(self.y_min.get()),
                y_max=int(self.y_max.get()),
                excluded_blocks=excluded,
                center_map=self.center_var.get()
            )
            messagebox.showinfo("Success", "Conversion completed successfully!")
        except Exception as e:
            log.exception("Conversion failed:")
            messagebox.showerror("Error", f"Conversion failed: {str(e)}")

if __name__ == "__main__":
    print("Starting UI...")
    app = BlockTextureUI()
    app.run()
