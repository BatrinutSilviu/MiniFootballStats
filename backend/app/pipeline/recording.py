"""
Filming advice for the next match, derived from what went wrong (or right)
while analyzing this one. Most accuracy problems come from how the video was
shot, and they are cheap to fix — so the app says exactly what to change.
"""


def recording_tips(quality: dict, video: dict) -> list[dict]:
    tips = []

    def tip(severity, title, detail):
        tips.append({"severity": severity, "title": title, "detail": detail})

    h = video.get("height")
    if h and h < 720:
        tip("high", "Film in at least 1080p",
            f"This video is {h}p. The ball is only a few pixels wide at this resolution, so it gets missed often. "
            "Set the phone camera to 1080p (or 4K if storage allows).")
    fps = video.get("fps")
    if fps and fps < 24:
        tip("medium", "Use a normal frame rate",
            f"This video has {fps:.0f} frames per second; fast shots blur between frames. 30 or 60 fps is ideal.")

    if quality["camera_registration_rate"] < 0.8:
        tip("high", "Pan more slowly, or fix the camera",
            f"The camera movement could only be followed in {round(quality['camera_registration_rate'] * 100)}% of the frames. "
            "Fast swings, zoom jumps and cuts lose the view. A phone on a tripod that shows the whole pitch works best.")

    if quality["ball_detected_rate"] < 0.3:
        tip("high", "Make the ball easier to see",
            f"The ball was found in only {round(quality['ball_detected_rate'] * 100)}% of the frames. "
            "Film from higher up (a stand, balcony or a 2–3 m tripod), closer to the halfway line, and avoid filming against "
            "the sun or floodlights. A brightly colored ball also helps.")

    size = quality.get("ball_size_norm") or 0
    if 0 < size < 0.5:
        tip("medium", "Get a bit closer or zoom in slightly",
            "The ball looks very small in the picture. Moving the camera closer to the touchline, or zooming in so the pitch fills the frame "
            "edge to edge, makes ball detection far more reliable.")

    if quality["goalkeepers_found"] < 2:
        tip("medium", "Keep both goals in view",
            "Not both goalkeepers could be identified, which is how the app knows which way each team attacks. "
            "Make sure both goal areas are visible regularly — ideally all the time.")

    if quality["tracks"] > 60:
        tip("low", "Fewer people crossing in front of the camera",
            f"{quality['tracks']} separate player tracks were created — players were often hidden and re-found. "
            "Placing the camera higher reduces players blocking each other. You can merge tracks of the same player in the Players table.")

    if not tips:
        tip("ok", "Great footage",
            "Camera, ball visibility and goalkeepers were all fine. Film the next match the same way.")
    return tips
