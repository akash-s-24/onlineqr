import os
import shutil
import sqlite3

images_dir = "images-of-events"
dest_dir = "static/images"

# Mapping from image filename (without extension) to exact Event Name in DB
mapping = {
    "Beatboxing": "Beat Boxing",
    "Content Creator": "Content Creator",
    "Photography": "Photography",
    "Solo Dance": "Solo Dance",
    "Tech Quiz": "Tech Quiz",
    "bgmi": "BGMI",
    "facepanting": "Face Painting",
    "freefire": "Free Fire",
    "get the shield": "Get the Shield",
    "groupdance": "Group Dance",
    "mad adds": "Mad Adds",
    "monoacting": "Mono Acting",
    "pencilesketch": "Pencil Sketching",
    "rampwalk": "Fashion Walk",
    "solo-singing": "Solo Singing",
    "Solo Singing": "Solo Singing",
    "Singing Solo": "Solo Singing",
    "singing": "Solo Singing",
}

# Ensure destination directory exists
os.makedirs(dest_dir, exist_ok=True)

conn = sqlite3.connect('eventmate.db')
cursor = conn.cursor()

for img_file in os.listdir(images_dir):
    if not os.path.isfile(os.path.join(images_dir, img_file)):
        continue
    
    name_without_ext, ext = os.path.splitext(img_file)
    event_name = mapping.get(name_without_ext)
    
    if event_name:
        # Normalize filename for web/database safety
        safe_img_file = img_file.replace(" ", "_")
        if event_name == "Group Dance":
            safe_img_file = "groupdance.jpeg"

        # Copy file
        src_path = os.path.join(images_dir, img_file)
        dest_path = os.path.join(dest_dir, safe_img_file)
        shutil.copy2(src_path, dest_path)
        if safe_img_file != img_file:
            # Also keep exact original name if needed
            shutil.copy2(src_path, os.path.join(dest_dir, img_file))
        
        # Update database
        cursor.execute("UPDATE events SET banner_image = ? WHERE event_name = ?", (safe_img_file, event_name))
        if event_name == "Solo Singing":
            cursor.execute("UPDATE events SET banner_image = ? WHERE event_name IN ('Solo Singing', 'Singing Solo', 'Singing')", (safe_img_file,))
        if event_name == "Fashion Walk":
            cursor.execute("UPDATE events SET banner_image = ? WHERE event_name IN ('Fashion Walk', 'Ramp Walk')", (safe_img_file,))
        if event_name == "Pencil Sketching":
            cursor.execute("UPDATE events SET banner_image = ? WHERE event_name IN ('Pencil Sketching', 'Pencil Sketch')", (safe_img_file,))
        
        # Also fix the "Python Test Update String" back to "BGMI"
        if event_name == "BGMI":
            cursor.execute("UPDATE events SET event_name = 'BGMI', banner_image = ? WHERE id = 1", (safe_img_file,))
        
        print(f"Updated {event_name} with {safe_img_file}")
    else:
        print(f"No mapping found for {img_file}")

conn.commit()
conn.close()
print("Done")
