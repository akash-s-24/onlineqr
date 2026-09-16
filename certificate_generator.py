import os
import io
import zipfile
import math
import uuid
import random
from PIL import Image, ImageDraw, ImageFont
import qrcode
from config import Config


def get_font_by_name(font_name, size, index=0):
    """Load system font from standard directories or default fallback."""
    paths_to_check = [
        font_name,
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'),
                     'Fonts', font_name),
        os.path.join('/Library/Fonts', font_name),
        os.path.join('/System/Library/Fonts', font_name),
        os.path.join('/System/Library/Fonts/Supplemental', font_name)
    ]

    # Handle Mac font name differences
    mac_alternatives = {
        "arialbd.ttf": "Arial Bold.ttf",
        "arial.ttf": "Arial.ttf",
        "timesbd.ttf": "Times New Roman Bold.ttf",
        "georgiab.ttf": "Georgia Bold.ttf",
        "georgiai.ttf": "Georgia Italic.ttf",
        "georgia.ttf": "Georgia.ttf",
        "segoescb.ttf": "Brush Script MT.ttf",
        "Nirmala.ttc": "Arial Unicode.ttf"
    }

    if font_name in mac_alternatives:
        alt_name = mac_alternatives[font_name]
        paths_to_check.extend([
            alt_name,
            os.path.join('/Library/Fonts', alt_name),
            os.path.join('/System/Library/Fonts', alt_name),
            os.path.join('/System/Library/Fonts/Supplemental', alt_name)
        ])

    for p in paths_to_check:
        try:
            if p.endswith('.ttc'):
                return ImageFont.truetype(p, size, index=index)
            return ImageFont.truetype(p, size)
        except Exception:
            continue

    # Ultimate fallback
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def draw_ribbon_banner(draw, cx, cy, width, height, bg_color=(20, 48, 100), border_color=(212, 175, 55)):
    """Draw an elegant royal blue rectangular banner with notched ribbon ends."""
    x1 = cx - width // 2
    y1 = cy - height // 2
    x2 = cx + width // 2
    y2 = cy + height // 2
    notch = 32

    # Left ribbon tail
    tail_left = [(x1 - notch, y1 + 10), (x1, y1), (x1, y2),
                 (x1 - notch, y2 - 10), (x1 - notch + 16, cy)]
    draw.polygon(tail_left, fill=(12, 28, 60), outline=border_color)

    # Right ribbon tail
    tail_right = [(x2 + notch, y1 + 10), (x2, y1), (x2, y2),
                  (x2 + notch, y2 - 10), (x2 + notch - 16, cy)]
    draw.polygon(tail_right, fill=(12, 28, 60), outline=border_color)

    # Main banner rectangle
    draw.rectangle([x1, y1, x2, y2], fill=bg_color,
                   outline=border_color, width=3)
    draw.rectangle([x1 + 4, y1 + 4, x2 - 4, y2 - 4],
                   outline=(254, 240, 138), width=1)


def draw_award_emblem(draw, cx, cy):
    """Draw a decorative academic award emblem with gold ribbons and the word AWARD."""
    # Ribbon streamers hanging down
    draw.polygon([(cx - 24, cy + 30), (cx - 44, cy + 115), (cx - 24, cy + 100),
                 (cx - 4, cy + 115)], fill=(180, 83, 9), outline=(212, 175, 55))
    draw.polygon([(cx + 4, cy + 30), (cx + 24, cy + 115), (cx + 44, cy + 100),
                 (cx + 64, cy + 115)], fill=(217, 119, 6), outline=(212, 175, 55))

    # Rosette / Starburst petals
    num_points = 24
    outer_r = 68
    inner_r = 58
    points = []
    for i in range(num_points * 2):
        angle = (i * math.pi) / num_points
        r = outer_r if (i % 2 == 0) else inner_r
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        points.append((px, py))
    draw.polygon(points, fill=(245, 158, 11), outline=(212, 175, 55))

    # Outer gold circle
    draw.ellipse([cx - 52, cy - 52, cx + 52, cy + 52],
                 fill=(254, 240, 138), outline=(180, 83, 9), width=3)
    # Inner navy ring
    draw.ellipse([cx - 42, cy - 42, cx + 42, cy + 42],
                 fill=(15, 23, 42), outline=(212, 175, 55), width=2)

    # Center text AWARD and Academic Year 2026-27
    f_award = get_font_by_name("timesbd.ttf", 17)
    f_star = get_font_by_name("arialbd.ttf", 13)
    f_year = get_font_by_name("arialbd.ttf", 11)
    draw.text((cx, cy - 14), "★  ★  ★",
              fill=(253, 224, 71), font=f_star, anchor="mm")
    draw.text((cx, cy + 2), "AWARD", fill=(255, 255, 255),
              font=f_award, anchor="mm")
    draw.text((cx, cy + 18), "2026-27", fill=(254,
              240, 138), font=f_year, anchor="mm")


def draw_student_silhouettes(draw, x_start, y_start):
    """
    Draw colorful silhouettes of students participating in sports and extracurricular
    activities along the bottom-right corner, backed by watercolor paint-splash effects.
    """
    # 1. Paint Splashes (Watercolor dots and pastel halos)
    splash_colors = [
        (254, 205, 211),  # Soft rose
        (186, 230, 253),  # Soft sky blue
        (254, 240, 138),  # Soft gold
        (221, 214, 254),  # Soft violet
        (167, 243, 208),  # Soft mint
        (253, 186, 116),  # Soft coral/orange
    ]
    random.seed(108)  # Deterministic aesthetics
    for i in range(28):
        sx = x_start + random.randint(-30, 460)
        sy = y_start + random.randint(-60, 200)
        sr = random.randint(16, 52)
        sc = splash_colors[i % len(splash_colors)]
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sc)

    # Small colorful scatter flecks
    accent_dots = [(225, 29, 72), (37, 99, 235), (217, 119, 6),
                   (124, 58, 237), (13, 148, 136)]
    for j in range(36):
        fx = x_start + random.randint(-40, 470)
        fy = y_start + random.randint(-70, 220)
        fr = random.randint(3, 8)
        fc = accent_dots[j % len(accent_dots)]
        draw.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=fc)

    # 2. Silhouettes of Students in Dynamic Sports & Extracurricular Poses
    c_navy = (15, 23, 42)
    c_slate = (30, 41, 59)
    c_blue = (30, 58, 138)
    c_gold = (234, 179, 8)

    # Pose 1: Sprinter / Track Athlete (Extracurricular Sports) - Left
    f1_x = x_start + 35
    f1_y = y_start + 70
    draw.ellipse([f1_x + 10, f1_y - 54, f1_x + 36, f1_y - 28], fill=c_slate)
    draw.polygon([(f1_x - 12, f1_y + 12), (f1_x + 16, f1_y - 28),
                 (f1_x + 30, f1_y - 22), (f1_x + 4, f1_y + 18)], fill=c_slate)
    draw.polygon([(f1_x + 20, f1_y - 22), (f1_x + 50, f1_y - 12),
                 (f1_x + 46, f1_y - 4), (f1_x + 16, f1_y - 16)], fill=c_slate)
    draw.polygon([(f1_x - 2, f1_y - 14), (f1_x - 26, f1_y + 10),
                 (f1_x - 22, f1_y + 14), (f1_x + 2, f1_y - 6)], fill=c_slate)
    draw.polygon([(f1_x + 2, f1_y + 14), (f1_x + 36, f1_y + 52),
                 (f1_x + 28, f1_y + 56), (f1_x - 4, f1_y + 18)], fill=c_slate)
    draw.polygon([(f1_x - 10, f1_y + 12), (f1_x - 34, f1_y + 58),
                 (f1_x - 26, f1_y + 60), (f1_x - 2, f1_y + 16)], fill=c_slate)

    # Pose 2: Football / Sports Athlete with Ball (Sports)
    f2_x = x_start + 145
    f2_y = y_start + 55
    draw.ellipse([f2_x - 14, f2_y - 56, f2_x + 14, f2_y - 28], fill=c_navy)
    draw.polygon([(f2_x - 20, f2_y + 24), (f2_x - 16, f2_y - 26),
                 (f2_x + 14, f2_y - 26), (f2_x + 20, f2_y + 24)], fill=c_navy)
    draw.polygon([(f2_x + 12, f2_y + 16), (f2_x + 48, f2_y + 36),
                 (f2_x + 44, f2_y + 44), (f2_x + 6, f2_y + 26)], fill=c_navy)
    # Sports ball in flight
    draw.ellipse([f2_x + 56, f2_y + 10, f2_x + 82, f2_y + 36],
                 fill=(255, 255, 255), outline=c_navy, width=2)
    draw.polygon([(f2_x + 65, f2_y + 19), (f2_x + 72, f2_y + 19), (f2_x + 76,
                 f2_y + 26), (f2_x + 69, f2_y + 31), (f2_x + 62, f2_y + 26)], fill=c_navy)

    # Pose 3: Celebrating Winner with Trophy (Extracurricular Achievement) - Center
    f3_x = x_start + 260
    f3_y = y_start + 35
    draw.ellipse([f3_x - 16, f3_y - 58, f3_x + 16, f3_y - 26], fill=c_navy)
    draw.polygon([(f3_x - 22, f3_y + 80), (f3_x - 18, f3_y - 24),
                 (f3_x + 18, f3_y - 24), (f3_x + 22, f3_y + 80)], fill=c_navy)
    draw.polygon([(f3_x - 16, f3_y - 20), (f3_x - 38, f3_y - 72),
                 (f3_x - 28, f3_y - 76), (f3_x - 6, f3_y - 22)], fill=c_navy)
    # Golden trophy
    tx, ty = f3_x - 42, f3_y - 102
    draw.polygon([(tx - 13, ty), (tx + 13, ty),
                 (tx + 7, ty + 22), (tx - 7, ty + 22)], fill=c_gold)
    draw.rectangle([tx - 4, ty + 22, tx + 4, ty + 30], fill=(202, 138, 4))
    draw.rectangle([tx - 9, ty + 30, tx + 9, ty + 36], fill=(161, 98, 7))

    # Pose 4: Cultural Dancer / Performer in Expressive Mudra Pose (Extracurricular Cultural)
    f4_x = x_start + 365
    f4_y = y_start + 50
    draw.ellipse([f4_x - 14, f4_y - 54, f4_x + 14, f4_y - 26], fill=c_blue)
    draw.polygon([(f4_x - 18, f4_y + 40), (f4_x - 14, f4_y - 24),
                 (f4_x + 14, f4_y - 24), (f4_x + 18, f4_y + 40)], fill=c_blue)
    draw.polygon([(f4_x + 12, f4_y - 20), (f4_x + 40, f4_y - 56),
                 (f4_x + 45, f4_y - 48), (f4_x + 16, f4_y - 14)], fill=c_blue)
    draw.polygon([(f4_x - 12, f4_y - 20), (f4_x - 38, f4_y - 52),
                 (f4_x - 34, f4_y - 58), (f4_x - 6, f4_y - 16)], fill=c_blue)

    # Pose 5: Tech / Student with Laptop & Book (Extracurricular Academic/Tech) - Far Right
    f5_x = x_start + 465
    f5_y = y_start + 70
    draw.ellipse([f5_x - 14, f5_y - 50, f5_x + 14, f5_y - 22], fill=c_slate)
    draw.polygon([(f5_x - 18, f5_y + 45), (f5_x - 16, f5_y - 20),
                 (f5_x + 16, f5_y - 20), (f5_x + 18, f5_y + 45)], fill=c_slate)
    draw.polygon([(f5_x - 25, f5_y + 10), (f5_x + 5, f5_y + 10),
                 (f5_x + 9, f5_y + 24), (f5_x - 20, f5_y + 24)], fill=(59, 130, 246))
    draw.polygon([(f5_x - 20, f5_y - 4), (f5_x - 20, f5_y + 10),
                 (f5_x - 9, f5_y + 10), (f5_x - 9, f5_y - 4)], fill=(147, 197, 253))


def generate_certificate(participant_name, event_name, event_date, college_name=None, cert_code=None, rank="1st", department="PCMC", semester="Second PUC", team_name=None):
    """
    Generate a high-quality, professional Certificate of Achievement inspired by the prompt.
    Returns: (cert_code, file_path, relative_url)
    """
    if not cert_code:
        prefix = "".join([w[0] for w in event_name.split() if w]).upper()[:3]
        cert_code = f"EM-2026-{prefix}-{uuid.uuid4().hex[:6].upper()}"

    # Canvas Dimensions: High-Res A4 Landscape (2480 x 1754 at 300 DPI equivalent)
    width, height = 2480, 1754
    bg_color = (255, 255, 255)  # Clean white background

    custom_template_path = os.path.join(
        "static", "uploads", "certificate_template.png")
    has_custom_template = os.path.exists(custom_template_path)

    if has_custom_template:
        try:
            img = Image.open(custom_template_path)
            if img.size != (width, height):
                img = img.resize((width, height), Image.LANCZOS)
            img = img.convert("RGB")
        except Exception as e:
            print(f"Error loading custom template: {e}")
            has_custom_template = False
            img = Image.new("RGB", (width, height), bg_color)
    else:
        img = Image.new("RGB", (width, height), bg_color)

    draw = ImageDraw.Draw(img)

    if not has_custom_template:

        # 1. Subtle Paper Texture / Fine Tint Background
        for r_step in range(40, 0, -2):
            shade = 255 - int(r_step * 0.12)
            draw.rectangle([(r_step, r_step), (width - r_step,
                           height - r_step)], outline=(shade, shade, shade))

        # 2. Elegant Dark Navy-Blue and Golden-Yellow Borders
        border_navy = (11, 25, 44)    # Deep Navy Blue
        border_gold = (212, 175, 55)   # Metallic Gold
        gold_accent = (234, 179, 8)    # Bright Gold Accent
        slate_border = (203, 213, 225)  # Soft Slate Border

        # Outer Thick Navy Border
        draw.rectangle([(28, 28), (width - 28, height - 28)],
                       outline=border_navy, width=16)

        # Inner Rich Gold Border
        draw.rectangle([(52, 52), (width - 52, height - 52)],
                       outline=border_gold, width=6)

        # Fine Inner Slate Guideline
        draw.rectangle([(66, 66), (width - 66, height - 66)],
                       outline=slate_border, width=2)

        # Inner Fine Gold Guideline
        draw.rectangle([(74, 74), (width - 74, height - 74)],
                       outline=(243, 210, 102), width=1)

        # 3. Corner Ornamental Filigrees (4 corners)
        corner_size = 55
        corners = [
            (66, 66),
            (width - 66 - corner_size, 66),
            (66, height - 66 - corner_size),
            (width - 66 - corner_size, height - 66 - corner_size)
        ]
        for cx_c, cy_c in corners:
            draw.rectangle([(cx_c, cy_c), (cx_c + corner_size, cy_c + corner_size)],
                           fill=(254, 240, 138), outline=border_gold, width=2)
            mid_x, mid_y = cx_c + corner_size // 2, cy_c + corner_size // 2
            draw.polygon([(mid_x, cy_c + 6), (cx_c + corner_size - 6, mid_y),
                         (mid_x, cy_c + corner_size - 6), (cx_c + 6, mid_y)], fill=border_navy)
            draw.ellipse([mid_x - 5, mid_y - 5, mid_x +
                         5, mid_y + 5], fill=gold_accent)

        # 4. Top-Right Award Emblem
        draw_award_emblem(draw, width - 210, 205)

        # 5. Top Center Institution Branding
        # Institution Name in bold uppercase serif lettering: "SHREE DAKSHA ACADEMY"
        f_inst = get_font_by_name("georgiab.ttf", 62)
        f_sub1 = get_font_by_name("georgia.ttf", 25)
        f_addr = get_font_by_name("georgia.ttf", 22)

        inst_name = "SHREE DAKSHA ACADEMY"
        draw.text((width // 2, 130), inst_name,
                  fill=border_navy, font=f_inst, anchor="mm")

        # Affiliation Subtitle: "Recognised by Govt. of Karnataka · Affiliated to Bangalore University · Approved by AICTE"
        sub1_text = "Recognised by Govt. of Karnataka · Affiliated to Bangalore University · Approved by AICTE"
        draw.text((width // 2, 195), sub1_text,
                  fill=(51, 65, 85), font=f_sub1, anchor="mm")

        # Address Line: "No. 526, Andrahalli Main Road, Opp. D Group Layout Arch, Bengaluru - 560 091"
        addr_text = "No. 526, Andrahalli Main Road, Opp. D Group Layout Arch, Bengaluru - 560 091"
        draw.text((width // 2, 238), addr_text,
                  fill=(100, 116, 139), font=f_addr, anchor="mm")

        # Decorative Divider Line with Center Diamond
        divider_y = 278
        draw.line([(width // 2 - 380, divider_y), (width // 2 +
                  380, divider_y)], fill=border_gold, width=3)
        draw.polygon([
            (width // 2, divider_y - 9),
            (width // 2 + 12, divider_y),
            (width // 2, divider_y + 9),
            (width // 2 - 12, divider_y)
        ], fill=border_navy, outline=gold_accent, width=2)

        # 6. Upper-Middle Section: Decorative Blue Rectangular Banner with Kannada Text & Academic Year: "ಸಾಂಸ್ಕೃತಿಕ 2026-27"
        banner_w = 460
        banner_h = 68
        banner_cx = width // 2
        banner_cy = 345
        draw_ribbon_banner(draw, banner_cx, banner_cy, banner_w,
                           banner_h, bg_color=(20, 48, 100), border_color=border_gold)

        # Bold Kannada Text inside Banner
        f_kannada = get_font_by_name("Nirmala.ttc", 38, index=1)
        kannada_title = "ಸಾಂಸ್ಕೃತಿಕ 2026-27"
        draw.text((banner_cx, banner_cy - 2), kannada_title,
                  fill=(255, 255, 255), font=f_kannada, anchor="mm")

        # 7. Prominently display: "Certificate of Achievement" in an elegant red calligraphic / serif font
        f_title = get_font_by_name("georgiab.ttf", 66)
        title_text = "Certificate of Achievement"
        # Subtle red drop shadow for rich calligraphic depth
        draw.text((width // 2 + 2, 442), title_text,
                  fill=(254, 202, 202), font=f_title, anchor="mm")
        draw.text((width // 2, 440), title_text, fill=(185, 28, 28),
                  font=f_title, anchor="mm")  # Elegant Red

        # Gold decorative flourish line beneath title
        draw.line([(width // 2 - 240, 484), (width // 2 + 240, 484)],
                  fill=border_gold, width=2)
        draw.ellipse([width // 2 - 6, 484 - 6, width //
                      2 + 6, 484 + 6], fill=border_gold)

    # 8. Formal Certificate Narrative Text:
    # "This is to Certify that Mr. / Ms. __________ has secured __________ of __________ BCA and has secured __________ Place in the __________ Event."
    f_body = get_font_by_name("georgiai.ttf", 35)
    f_handwriting = get_font_by_name("segoescb.ttf", 39)
    f_handwriting_name = get_font_by_name("segoescb.ttf", 47)
    blue_ink = (24, 58, 140)  # Natural dark blue handwritten ink

    # Format values
    p_name = participant_name.strip()

    # Secured details (e.g. I Class Distinction, First Class, Merit, etc.)
    if rank and rank.lower() in ('1st', '2nd', '3rd', 'first', 'second', 'third', 'winner'):
        sec_details = "I Class Distinction"
    else:
        sec_details = "Active Participation"

    # Course name default to BCA per prompt specification
    course_suffix = "BCA"

    # Clean semester
    sem_text = semester.strip() if semester else "Second PUC"

    # Place text formatting
    place_text = rank.strip() if rank else "1st"
    if place_text.lower() in ('1', '1st', 'first'):
        place_text = "1st"
    elif place_text.lower() in ('2', '2nd', 'second'):
        place_text = "2nd"
    elif place_text.lower() in ('3', '3rd', 'third'):
        place_text = "3rd"
    elif place_text.lower() in ('winner', 'winners'):
        place_text = "1st"
    elif place_text.lower() == 'participation':
        place_text = "Merit"

    if has_custom_template:
        import json
        
        f_handwriting = get_font_by_name("segoescb.ttf", 39)
        f_handwriting_name = get_font_by_name("segoescb.ttf", 47)
        blue_ink = (24, 58, 140)
        border_navy = (11, 25, 44)
        
        coords = {
            'name_x': 1240, 'name_y': 610,
            'rank_x': 1240, 'rank_y': 740,
            'event_x': 1240, 'event_y': 870,
            'date_x': 115, 'date_y': 1540
        }
        coords_path = os.path.join(
            "static", "uploads", "cert_coordinates.json")
        if os.path.exists(coords_path):
            try:
                with open(coords_path, 'r') as f:
                    coords.update(json.load(f))
            except Exception:
                pass

        # Print only raw variables at specified coordinates
        draw.text((coords['name_x'], coords['name_y']), p_name,
                  fill=blue_ink, font=f_handwriting_name, anchor="mm")
        draw.text((coords['rank_x'], coords['rank_y']), place_text,
                  fill=blue_ink, font=f_handwriting, anchor="mm")
        draw.text((coords['event_x'], coords['event_y']), event_name,
                  fill=blue_ink, font=f_handwriting, anchor="mm")
        draw.text((coords['date_x'], coords['date_y']), event_date,
                  fill=border_navy, font=get_font_by_name("arialbd.ttf", 14))

        if team_name:
            team_display = f"(Team: {team_name})"
            draw.text((coords['event_x'], coords['event_y'] + 60), team_display, fill=(
                71, 85, 105), font=get_font_by_name("georgiai.ttf", 28), anchor="mm")

    else:

        # ----------------------------------------------------
        # Line 1: "This is to Certify that Mr. / Ms. ____________________"
        # ----------------------------------------------------
        y_l1 = 610
        l1_prefix = "This is to Certify that Mr. / Ms. "
        w_l1_pre = draw.textbbox((0, 0), l1_prefix, font=f_body)[2]
        w_l1_name = draw.textbbox((0, 0), p_name, font=f_handwriting_name)[2]
        fill_name_w = max(360, w_l1_name + 40)
        total_l1_w = w_l1_pre + fill_name_w
        start_x1 = width // 2 - total_l1_w // 2

        # Draw Line 1 Prefix
        draw.text((start_x1, y_l1), l1_prefix, fill=(51, 65, 85), font=f_body)

        # Draw Candidate Name & Underline
        name_x = start_x1 + w_l1_pre + 15
        draw.text((name_x + (fill_name_w - w_l1_name) // 2 - 15, y_l1 - 10),
                  p_name, fill=blue_ink, font=f_handwriting_name)
        draw.line([(name_x, y_l1 + 45), (name_x + fill_name_w, y_l1 + 45)],
                  fill=(148, 163, 184), width=2)

        # ----------------------------------------------------
        # Line 2: "has secured ___________ of ___________ BCA"
        # ----------------------------------------------------
        y_l2 = 745
        l2_pre = "has secured "
        l2_mid = " of "
        l2_suf = f" {course_suffix}"

        w_l2_pre = draw.textbbox((0, 0), l2_pre, font=f_body)[2]
        w_sec = draw.textbbox((0, 0), sec_details, font=f_handwriting)[2]
        w_l2_mid = draw.textbbox((0, 0), l2_mid, font=f_body)[2]
        w_sem = draw.textbbox((0, 0), sem_text, font=f_handwriting)[2]
        w_l2_suf = draw.textbbox((0, 0), l2_suf, font=f_body)[2]

        fill1_w = max(260, w_sec + 26)
        fill2_w = max(190, w_sem + 26)
        total_l2_w = w_l2_pre + fill1_w + w_l2_mid + fill2_w + w_l2_suf
        start_x2 = width // 2 - total_l2_w // 2

        cur_x2 = start_x2
        draw.text((cur_x2, y_l2), l2_pre, fill=(51, 65, 85), font=f_body)
        cur_x2 += w_l2_pre

        # Secured fill-in
        draw.text((cur_x2 + (fill1_w - w_sec) // 2, y_l2 - 6),
                  sec_details, fill=blue_ink, font=f_handwriting)
        draw.line([(cur_x2 + 4, y_l2 + 40), (cur_x2 + fill1_w -
                  4, y_l2 + 40)], fill=(148, 163, 184), width=2)
        cur_x2 += fill1_w

        draw.text((cur_x2, y_l2), l2_mid, fill=(51, 65, 85), font=f_body)
        cur_x2 += w_l2_mid

        # Semester fill-in
        draw.text((cur_x2 + (fill2_w - w_sem) // 2, y_l2 - 6),
                  sem_text, fill=blue_ink, font=f_handwriting)
        draw.line([(cur_x2 + 4, y_l2 + 40), (cur_x2 + fill2_w -
                  4, y_l2 + 40)], fill=(148, 163, 184), width=2)
        cur_x2 += fill2_w

        draw.text((cur_x2, y_l2), l2_suf, fill=(51, 65, 85), font=f_body)

        # ----------------------------------------------------
        # Line 3: "and has secured ___________ Place in the ______________________ Event."
        # ----------------------------------------------------
        y_l3 = 870
        l3_pre = "and has secured "
        l3_mid = " Place in the "
        l3_ev = event_name
        l3_suf = " Event."

        w_l3_pre = draw.textbbox((0, 0), l3_pre, font=f_body)[2]
        w_place = draw.textbbox((0, 0), place_text, font=f_handwriting)[2]
        w_l3_mid = draw.textbbox((0, 0), l3_mid, font=f_body)[2]
        w_ev = draw.textbbox((0, 0), l3_ev, font=f_handwriting)[2]
        w_l3_suf = draw.textbbox((0, 0), l3_suf, font=f_body)[2]

        fill3_w = max(110, w_place + 20)
        fill4_w = max(260, w_ev + 26)
        total_l3_w = w_l3_pre + fill3_w + w_l3_mid + fill4_w + w_l3_suf
        start_x3 = width // 2 - total_l3_w // 2

        cur_x3 = start_x3
        draw.text((cur_x3, y_l3), l3_pre, fill=(51, 65, 85), font=f_body)
        cur_x3 += w_l3_pre

        # Place fill-in
        draw.text((cur_x3 + (fill3_w - w_place) // 2, y_l3 - 6),
                  place_text, fill=blue_ink, font=f_handwriting)
        draw.line([(cur_x3 + 4, y_l3 + 40), (cur_x3 + fill3_w -
                  4, y_l3 + 40)], fill=(148, 163, 184), width=2)
        cur_x3 += fill3_w

        draw.text((cur_x3, y_l3), l3_mid, fill=(51, 65, 85), font=f_body)
        cur_x3 += w_l3_mid

        # Event fill-in
        draw.text((cur_x3 + (fill4_w - w_ev) // 2, y_l3 - 6),
                  l3_ev, fill=blue_ink, font=f_handwriting)
        draw.line([(cur_x3 + 4, y_l3 + 40), (cur_x3 + fill4_w -
                  4, y_l3 + 40)], fill=(148, 163, 184), width=2)
        cur_x3 += fill4_w

        draw.text((cur_x3, y_l3), l3_suf, fill=(51, 65, 85), font=f_body)

        # Optional team mention if group event
        if team_name:
            y_team = 965
            team_display = f"(Team: {team_name})"
            draw.text((width // 2, y_team), team_display, fill=(71, 85, 105),
                      font=get_font_by_name("georgiai.ttf", 28), anchor="mm")

    # 9. Bottom-Right Corner: Colorful silhouettes & paint splashes of students in sports & extracurriculars
    if not has_custom_template:
        draw_student_silhouettes(draw, width - 590, height - 380)

        # 10. Bottom Section: Three Signature Sections (hod, lectures, Principal)
        f_sig_script = get_font_by_name("segoescb.ttf", 36)
        f_sig_label = get_font_by_name("georgiab.ttf", 28)
        f_sig_sub = get_font_by_name("georgia.ttf", 20)
        sig_y = height - 260

        # Signature 1: HOD (Left-Center)
        sig1_x = 640
        draw.line([(sig1_x - 140, sig_y), (sig1_x + 140, sig_y)],
                  fill=(148, 163, 184), width=2)
        draw.text((sig1_x, sig_y - 45), "Prof. Chethana",
                  fill=(30, 58, 138), font=f_sig_script, anchor="mm")
        draw.text((sig1_x, sig_y + 30), "hod", fill=border_navy,
                  font=f_sig_label, anchor="mm")
        draw.text((sig1_x, sig_y + 60), "Head of Department",
                  fill=(100, 116, 139), font=f_sig_sub, anchor="mm")

        # Signature 2: Lectures / Faculty Coordinator (Center)
        sig2_x = 1120
        draw.line([(sig2_x - 140, sig_y), (sig2_x + 140, sig_y)],
                  fill=(148, 163, 184), width=2)
        draw.text((sig2_x, sig_y - 45), "K. Srinivas Rao",
                  fill=(30, 58, 138), font=f_sig_script, anchor="mm")
        draw.text((sig2_x, sig_y + 30), "lectures",
                  fill=border_navy, font=f_sig_label, anchor="mm")
        draw.text((sig2_x, sig_y + 60), "Faculty Coordinator",
                  fill=(100, 116, 139), font=f_sig_sub, anchor="mm")

        # Signature 3: Principal (Right-Center)
        sig3_x = 1600
        draw.line([(sig3_x - 140, sig_y), (sig3_x + 140, sig_y)],
                  fill=(148, 163, 184), width=2)
        draw.text((sig3_x, sig_y - 45), "Dr. Ramesh Hegde",
                  fill=(30, 58, 138), font=f_sig_script, anchor="mm")
        draw.text((sig3_x, sig_y + 30), "Principal",
                  fill=border_navy, font=f_sig_label, anchor="mm")
        draw.text((sig3_x, sig_y + 60), "Shree Daksha Academy",
                  fill=(100, 116, 139), font=f_sig_sub, anchor="mm")

        # 11. Event Date Details (Bottom-Left Corner)
        f_v1 = get_font_by_name("arial.ttf", 13)
        f_v2 = get_font_by_name("arialbd.ttf", 14)
        draw.text((115, height - 212), "Awarded On:",
                  fill=(100, 116, 139), font=f_v1)
        draw.text((115, height - 190),
                  f"{event_date}", fill=border_navy, font=f_v2)

    # Save to certificates directory
    os.makedirs(Config.CERTIFICATE_FOLDER, exist_ok=True)
    filename = f"{cert_code}.png"
    filepath = os.path.join(Config.CERTIFICATE_FOLDER, filename)
    img.save(filepath, "PNG", quality=95)

    relative_url = f"/certificates/{filename}"
    return cert_code, filepath, relative_url


if __name__ == '__main__':
    code, path, rel = generate_certificate(
        participant_name="Varshitha H",
        event_name="Binary Brains",
        event_date="18-Sep-2026",
        rank="1st",
        department="BCA",
        semester="Second PUC",
        team_name="CyberKnights"
    )
    print(f"Sample certificate generated successfully: {code} at {path}")


def generate_team_certificates_zip(team_members_str, event_name, event_date, college_name=None, cert_code_base=None, department="PCMC", semester="Second PUC", team_name=None):
    """
    Generates a PDF certificate for each member in the team_members_str,
    and returns a ZIP file containing all PDFs as raw bytes.
    """
    if not team_members_str:
        return b""

    members = [m.strip() for m in team_members_str.split(',') if m.strip()]
    if not cert_code_base:
        cert_code_base = "GRP" + uuid.uuid4().hex[:8].upper()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for idx, member in enumerate(members):
            # Generate the PNG file
            member_cert_code = f"{cert_code_base}_{idx+1}"
            _, png_filepath, _ = generate_certificate(
                participant_name=member,
                event_name=event_name,
                event_date=event_date,
                college_name=college_name,
                cert_code=member_cert_code,
                department=department,
                semester=semester,
                team_name=team_name
            )

            # Convert PNG to PDF in memory using Pillow
            try:
                img = Image.open(png_filepath)
                pdf_buffer = io.BytesIO()
                img.convert('RGB').save(
                    pdf_buffer, format='PDF', resolution=100.0)
                pdf_bytes = pdf_buffer.getvalue()

                # Add to ZIP
                safe_name = member.replace(" ", "_")
                zip_file.writestr(
                    f"{safe_name}_{event_name}_Certificate.pdf", pdf_bytes)

                # Optionally delete the temporary PNG to save space, but we might want to keep the leader's PNG
                # We'll just leave it since the user's disk has space and it might be used.
            except Exception as e:
                print(f"Error converting cert for {member}: {e}")

    return zip_buffer.getvalue()
