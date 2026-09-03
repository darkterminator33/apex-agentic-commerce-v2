from manim import *

# Red Bull Racing Two-Tone Theme
BG = "#0B1021"          # Deep Matte Navy
RBR_RED = "#EE0026"     # Racing Red
WHITE_TXT = "#f5f5f5"
GRAY_TXT = "#9a9a9a"
DIM_TXT = "#6a7382"     

config.background_color = BG
config.pixel_width = 3840
config.pixel_height = 2160
config.frame_width = 14.2222
config.frame_height = 8


class TitleScene(Scene):
    def construct(self):
        # Top accent bar (full width, thin)
        top_bar = Rectangle(
            width=config.frame_width, height=0.09,
            fill_color=RBR_RED, fill_opacity=1, stroke_width=0
        ).to_edge(UP, buff=0).shift(UP * 0.045)

        # Swapped to Helvetica Neue to fix kerning issues with variable fonts
        title = Text("Apex F1 Store", font="Helvetica Neue", weight=BOLD, font_size=76, color=WHITE_TXT)
        subtitle = Text(
            "Agentic commerce, bounded and gated end to end",
            font="Helvetica Neue", font_size=30, color=GRAY_TXT
        )
        divider = Line(LEFT * 1.6, RIGHT * 1.6, color=RBR_RED, stroke_width=3)
        track = Text(
            "Razorpay Buildathon — Track 01: AI Growth & Agentic Commerce",
            font="Helvetica Neue", font_size=24, color=GRAY_TXT
        )
        footer = Text(
            "One enforcement engine. Two front doors. A trust boundary neither can fake through.",
            font="Helvetica Neue", font_size=20, slant=ITALIC, color=DIM_TXT
        )

        title.move_to(UP * 0.9)
        subtitle.next_to(title, DOWN, buff=0.45)
        divider.next_to(subtitle, DOWN, buff=0.55)
        track.next_to(divider, DOWN, buff=0.55)
        footer.to_edge(DOWN, buff=0.9)

        # --- Streamlined Animation Sequence ---
        self.play(GrowFromEdge(top_bar, LEFT), run_time=0.4)

        # Write animation for the main title (2 seconds)
        self.play(Write(title), run_time=2.0)

        # Grouping the rest into smooth, fast parallel fades to save time
        self.play(
            FadeIn(subtitle, shift=UP * 0.1),
            Create(divider),
            run_time=0.6
        )

        # Track shifts up slightly, footer strictly fades in place
        self.play(
            FadeIn(track, shift=UP * 0.1),
            FadeIn(footer),
            run_time=0.6
        )

        # Hold all elements on screen for 10 extra seconds instead of fading out
        self.wait(10)