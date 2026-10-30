"""Six authored cloth poses, with a fixed header and a small delayed hem."""


def curtain_strips(frame, config):
    sequence = config["curtain_sequence"]
    period = config["period_frames"]
    follow = config.get("curtain_follow_frames", 5)
    strips = [("curtain_0", 0, 60)]
    for row in range(60, 90, 5):
        delay = round(follow * (row - 60) / 25)
        pose = sequence[((frame - delay) % period) * len(sequence) // period]
        strips.append((f"curtain_{pose}", row, 5))
    return strips
