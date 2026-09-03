from manim import *
import os
import urllib.request
import urllib.parse

# --- Auto-Downloader for Apple Emojis (High-Res PNGs) ---
def get_apple_emoji(emoji_char, name):
    path = f"{name}.png"
    # Download the Apple-style PNG if it's not already in the folder
    if not os.path.exists(path):
        encoded = urllib.parse.quote(emoji_char)
        url = f"https://emojicdn.elk.sh/{encoded}?style=apple"
        
        # We use a standard User-Agent so the CDN doesn't block the Python script
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
                out_file.write(response.read())
        except Exception as e:
            print(f"Error downloading {emoji_char}: {e}")
    
    # Load into Manim as an ImageMobject (supports transparent PNGs)
    if os.path.exists(path):
        return ImageMobject(path).scale_to_fit_height(0.4)
    return Text(emoji_char) # Safe fallback just in case


# --- Apple x Red Bull Minimalist Theme ---
BG = "#0B1021"            # Deep Matte Navy
SYS_BLUE = "#007AFF"      # Apple System Blue
RBR_RED = "#B80023"       # Richer, deeper racing red
COOL_YELLOW = "#E0CF8A"   # Cooler, softer pastel yellow
DARK_PANEL = "#121929"    # Very subtle panel distinction
WHITE_TXT = "#f5f5f5"
DIM_TXT = "#8A94A6"       

config.background_color = BG

class ArchDiagram(Scene):
    def construct(self):
        # 1. Content Generation (Changed VGroup -> Group to allow PNGs)
        # -------------------------------------
        
        # 👤 Silhouette
        emoji_h = get_apple_emoji("👤", "emoji_human")
        txt_h1 = Text("Human buyer", font="Helvetica Neue", color=WHITE_TXT).scale(0.55)
        line_h = Group(emoji_h, txt_h1).arrange(RIGHT, buff=0.25)
        txt_h2 = Text("mk3.py — Streamlit UI", font="Helvetica Neue", color=WHITE_TXT).scale(0.35)
        content_human = Group(line_h, txt_h2).arrange(DOWN, buff=0.2)

        # 👾 Retro Alien/Bot
        emoji_ai = get_apple_emoji("👾", "emoji_alien")
        txt_ai1 = Text("AI agent buyer", font="Helvetica Neue", color=WHITE_TXT).scale(0.55)
        line_ai = Group(emoji_ai, txt_ai1).arrange(RIGHT, buff=0.25)
        txt_ai2 = Text("agent_api.py — FastAPI", font="Helvetica Neue", color=WHITE_TXT).scale(0.35)
        content_ai = Group(line_ai, txt_ai2).arrange(DOWN, buff=0.2)

        # 🛡️ Shield
        emoji_core = get_apple_emoji("🛡️", "emoji_shield")
        txt_core1 = Text("core.py — enforcement engine", font="Helvetica Neue", color=SYS_BLUE).scale(0.55)
        line_core = Group(emoji_core, txt_core1).arrange(RIGHT, buff=0.25)
        txt_core2 = Text("Catalog • stock • pricing\nMandate verification • audit log", font="Helvetica Neue", color=WHITE_TXT, line_spacing=1).scale(0.4)
        txt_core3 = Text("Public key only — no private key here", font="Helvetica Neue", color=COOL_YELLOW).scale(0.4)
        content_core = Group(line_core, txt_core2, txt_core3).arrange(DOWN, buff=0.4)

        # 🔑 Key
        emoji_w = get_apple_emoji("🔑", "emoji_key")
        txt_w1 = Text("wallet_authority.py", font="Helvetica Neue", color=BLACK).scale(0.5)
        line_w = Group(emoji_w, txt_w1).arrange(RIGHT, buff=0.25)
        txt_w2 = Text("Signs mandates\nHolds the private key", font="Helvetica Neue", color=BLACK, line_spacing=1).scale(0.4)
        content_wallet = Group(line_w, txt_w2).arrange(DOWN, buff=0.3)

        # Razorpay Vector Handling
        svg_path = "/Users/aayush/Movies/Offline/Git/Manim/Razorpay_logo.svg"
        if os.path.exists(svg_path):
            rzp_icon = SVGMobject(svg_path).scale_to_fit_height(0.55)
        elif os.path.exists("Razorpay_logo.svg"):
            rzp_icon = SVGMobject("Razorpay_logo.svg").scale_to_fit_height(0.55)
        else:
            rzp_icon = get_apple_emoji("💳", "emoji_card").scale_to_fit_height(0.55)
        
        if isinstance(rzp_icon, SVGMobject):
            rzp_icon.set_stroke(width=0, opacity=0)
            if len(rzp_icon) > 1:
                rzp_icon[0].set_fill("#02042B")      
                rzp_icon[1:].set_fill("#0C2340")     
                rzp_icon[0].set_fill("#008ECC")

        txt_rzp2 = Text("Test mode payment link", font="Helvetica Neue", color=BLACK).scale(0.35)
        content_rzp = Group(rzp_icon, txt_rzp2).arrange(DOWN, buff=0.3)

        # 2. Box Container Assembly
        # -------------------------------------
        def create_box(content, bg_color, w, h, stroke_c=None, stroke_w=0):
            rect = RoundedRectangle(
                corner_radius=0.2, width=w, height=h, 
                fill_color=bg_color, fill_opacity=1, 
                stroke_color=stroke_c or bg_color, stroke_width=stroke_w
            )
            content.move_to(rect.get_center())
            return Group(rect, content)

        human_box = create_box(content_human, SYS_BLUE, 4.8, 1.4)
        ai_box = create_box(content_ai, RBR_RED, 4.8, 1.4)
        core_box = create_box(content_core, DARK_PANEL, 7.0, 3.0, stroke_c=SYS_BLUE, stroke_w=1.5)
        wallet_box = create_box(content_wallet, COOL_YELLOW, 4.4, 1.8)
        
        rzp_box = create_box(content_rzp, WHITE_TXT, 4.6, 1.7)
        rzp_rect = rzp_box[0]
        rzp_content = rzp_box[1]

        # 3. Layout & Positioning
        # -------------------------------------
        top_row = Group(human_box, ai_box).arrange(RIGHT, buff=2.2)
        core_box.next_to(top_row, DOWN, buff=1.6)
        wallet_box.next_to(core_box, LEFT, buff=2.2)
        rzp_box.next_to(core_box, DOWN, buff=1.6)

        # 4. Routing Lines & Arrows
        # -------------------------------------
        mid_y = (top_row.get_bottom()[1] + core_box.get_top()[1]) / 2
        
        path_h = VMobject(color=DIM_TXT, stroke_width=2.5)
        path_h.set_points_as_corners([human_box.get_bottom(), [human_box.get_x(), mid_y, 0], [core_box.get_x(), mid_y, 0]])
        
        path_ai = VMobject(color=DIM_TXT, stroke_width=2.5)
        path_ai.set_points_as_corners([ai_box.get_bottom(), [ai_box.get_x(), mid_y, 0], [core_box.get_x(), mid_y, 0]])
        
        arrow_c = Arrow([core_box.get_x(), mid_y, 0], core_box.get_top(), color=DIM_TXT, buff=0, stroke_width=2.5, max_tip_length_to_length_ratio=0.2)
        
        arrow_w = Arrow(wallet_box.get_right(), core_box.get_left(), color=DIM_TXT, buff=0, stroke_width=2.5)
        pub_key_label = Text("Public Key\nOnly", font="Helvetica Neue", color=WHITE_TXT, line_spacing=1).scale(0.35)
        pub_key_label.next_to(arrow_w, UP, buff=0.2)
        
        arrow_r = Arrow(core_box.get_bottom(), rzp_box.get_top(), color=DIM_TXT, buff=0, stroke_width=2.5)

        # 5. Grouping & Bounds Fitting
        # -------------------------------------
        entire_diagram = Group(
            top_row, core_box, wallet_box, rzp_box, 
            path_h, path_ai, arrow_c, 
            arrow_w, pub_key_label, arrow_r
        )
        
        entire_diagram.scale_to_fit_height(config.frame_height - 2.6)
        entire_diagram.move_to(UP * 0.4) 

        # 6. Footer
        # -------------------------------------
        footer = Text(
            "One enforcement engine, two front doors — the wallet authority is the only\ncode that ever touches a private key; the merchant only verifies signatures.",
            font="Helvetica Neue", color=DIM_TXT, line_spacing=1.2
        ).scale(0.35)
        footer.to_edge(DOWN, buff=0.8)

        # 7. Animation Flow
        # -------------------------------------
        self.play(FadeIn(human_box, shift=DOWN * 0.2), FadeIn(ai_box, shift=DOWN * 0.2), run_time=1.2)
        
        self.play(Create(path_h), Create(path_ai), run_time=0.6)
        self.play(Create(arrow_c), run_time=0.3)
        
        self.play(FadeIn(core_box, scale=0.95), run_time=1)
        
        self.play(
            FadeIn(wallet_box, shift=RIGHT * 0.2),
            Create(arrow_w),
            Write(pub_key_label),
            run_time=1.2
        )
        
        self.play(Create(arrow_r), FadeIn(rzp_rect, shift=UP * 0.2), run_time=0.8)
        self.play(
            FadeIn(rzp_icon, scale=0.95),
            Write(txt_rzp2),
            run_time=1.2
        )
        
        self.play(FadeIn(footer), run_time=1)
        self.wait(10)