#!/usr/bin/env python3
"""Convert Threema export to nicely formatted HTML."""

import argparse
from datetime import datetime
import html
import os
import re
import shutil
import sys


def make_links(text, media_folder, thumb_width, found_files=None):
    # Sanitize XML characters FIRST
    text = html.escape(text)

    # Process images for inline display
    def img_repl(match):
        filename = match.group(1)
        if found_files is not None:
            found_files.append(filename)
        return f'<br/><a href="{media_folder}{filename}"><img src="{media_folder}{filename}" alt="Image" width="{thumb_width}"/></a>'

    text = re.sub(r"&lt;(.+\.(?:jpe?g|png))&gt;", img_repl, text)

    # Process other files as links
    def file_repl(match):
        filename = match.group(1)
        if found_files is not None:
            found_files.append(filename)
        return f'<a href="{media_folder}{filename}">{filename}</a>'

    text = re.sub(r"&lt;(.+\.(?:mp4|pdf|vcf))&gt;", file_repl, text)

    # Process hyperlinks
    def url_repl(match):
        url = match.group(1)
        return f'<a href="{url}">{url}</a>'

    text = re.sub(r"(https?://[^ ]+)", url_repl, text)

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Convert Threema exports to nicely formatted HTML."
    )
    parser.add_argument(
        "-f",
        "--from-date",
        type=int,
        default=19700101,
        help="Start of date range to include (default: 19700101)",
    )
    parser.add_argument(
        "-t",
        "--to-date",
        type=int,
        default=20701231,
        help="End of date range to include (default: 20701231)",
    )
    parser.add_argument(
        "-T", "--title", default="Threema Export", help="HTML title"
    )
    parser.add_argument(
        "-n", "--name", default="", help="Name of exporter to substitute for 'Ich'"
    )
    parser.add_argument(
        "-m", "--media-folder", default="./media/", help="Media folder"
    )
    parser.add_argument(
        "-s", "--style-file", default="./lib/default.css", help="CSS style file"
    )
    parser.add_argument(
        "-w", "--width", type=int, default=480, help="Image width"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    parser.add_argument("inputfile", help="Exported Threema messages file (.txt)")

    args = parser.parse_args()

    input_dir = os.path.dirname(os.path.abspath(args.inputfile))

    message_start_pattern = re.compile(
        r"^\[(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2}:\d{2})\]\s*(.*)"
    )

    old_date = ""
    pending_msg = False
    onr = 0

    def close_msg_div(date_time_str):
        print("\t\t\t</p>")
        print('\t\t\t<p class="timestamp">')
        print(f"\t\t\t\t{date_time_str}")
        print("\t\t\t</p>")
        print("\t\t</div>")

    def copy_files(files):
        for filename in files:
            src_path = os.path.join(input_dir, filename)
            dst_path = os.path.join(args.media_folder, filename)
            if os.path.exists(src_path):
                if args.verbose:
                    print(
                        f"Copying {src_path} to {dst_path}", file=sys.stderr
                    )
                try:
                    os.makedirs(args.media_folder, exist_ok=True)
                    shutil.copy(src_path, dst_path)
                except Exception as e:
                    print(f"Error copying file: {e}", file=sys.stderr)
            else:
                if args.verbose:
                    print(f"File not found: {src_path}", file=sys.stderr)

    # Print file header
    print("<!DOCTYPE html>")
    print("<html>")
    print("<head>")
    print(
        '\t<meta name="generator" content="threema2html.py (migrated from AWK)">'
    )
    print(f"\t<title>{args.title}</title>")
    print(f'\t<link rel="stylesheet" type="text/css" href="{args.style_file}">')
    print("</head>")
    print("<body>")

    current_msg_timestamp = ""

    try:
        with open(args.inputfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                match = message_start_pattern.match(line)
                if match:
                    date_str = match.group(1)
                    time_str = match.group(2)
                    rest = match.group(3)

                    # Parse date for filtering
                    try:
                        current_date = datetime.strptime(date_str, "%d.%m.%Y")
                        date_int = int(current_date.strftime("%Y%m%d"))
                    except ValueError:
                        print(
                            f"Error parsing date: {date_str}", file=sys.stderr
                        )
                        continue

                    if date_int < args.from_date or date_int > args.to_date:
                        continue

                    # Parse user and message
                    parts = rest.split(": ", 1)
                    if len(parts) > 1:
                        user = parts[0]
                        msg = parts[1]
                    else:
                        user = "(Unknown)"
                        msg = rest

                    if pending_msg:
                        close_msg_div(current_msg_timestamp)

                    if date_str != old_date:
                        if pending_msg:
                            print("\t</div>")  # Close previous date div

                        print('\t<div class="date">')
                        print(f"\t\t<h2>{date_str}</h2>")
                        old_date = date_str

                    # Start new message
                    user_class = user
                    display_name = user
                    if args.name and user == "Ich":
                        user_class = f"Ich {args.name}"
                        display_name = args.name

                    print(f'\t\t<div class="{user_class}">')
                    print(f"\t\t\t<h3>{display_name}</h3>")

                    found_files = []
                    processed_msg = make_links(
                        msg, args.media_folder, args.width, found_files
                    )
                    copy_files(found_files)

                    print('\t\t\t<p class="msg">')
                    print(f"\t\t\t\t{processed_msg}")

                    current_msg_timestamp = f"{date_str}, {time_str}"
                    pending_msg = True
                    onr += 1
                else:
                    if pending_msg:
                        # Continuation line
                        found_files = []
                        processed_line = make_links(
                            line, args.media_folder, args.width, found_files
                        )
                        copy_files(found_files)
                        print(f"\t\t\t\t</br>{processed_line}")
    except FileNotFoundError:
        print(f"Error: File not found: {args.inputfile}", file=sys.stderr)
        sys.exit(1)

    if pending_msg:
        close_msg_div(current_msg_timestamp)
        print("\t</div>")  # Close date div

    print("</body>")
    print("</html>")

    print(f"{onr} output messages.", file=sys.stderr)


if __name__ == "__main__":
    main()
