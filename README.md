threema2html
============

Project moved to Codeberg: https://codeberg.org/harveyk/threema2html

Convert a Threema chat export to nicely formatted, long term preservation friendly HTML

https://github.com/hkramski/threema2html

1. For long-running exports, make sure that your smartphone does not go into standby mode during the 
   export process otherwise you may end up with a corrupted .zip file.
2. Export a chat in Threema (including media files), see https://threema.ch/en/faq/chatexport.
3. Unpack the .zip file (without any subfolders) into the folder where this script lives.
4. `python3 threema2html.py messages-chatname.txt > index.html`
   (See `python3 threema2html.py -h` for more options.)

   For large chats, you can split the output into multiple files by year or month:
   `python3 threema2html.py --split year messages-chatname.txt`
   or
   `python3 threema2html.py --split month messages-chatname.txt`
   This will automatically generate an `index.html` (with global cross-file search backed by a lazy-loaded `search_index.js`) linking to the split files.

   Note: Referenced media files will be automatically copied to the `./media/` folder if they are found in the same directory as the input file.
5. Adjust `./lib/default.css`.

Embedded Search
---------------

Generated HTML pages include a fast, offline-compatible (`file://`) JavaScript search engine by default:

- **Open search**: Click the floating search button in the top-right corner, or press `/` or `Cmd`/`Ctrl`+`K` (`Cmd`/`Ctrl`+`F` remains native browser find).
- **Smart matching**: Space-separated words match anywhere in a message (AND), `"quotes"` match exact phrases, and a **Sender** dropdown narrows by participant.
- **Navigation & filtering**: Starts at the most recent match (`Enter` / `↑` steps to older matches, `Shift+Enter` / `↓` steps to newer matches, `Esc` clears and closes). Toggle **Filter** to hide non-matching messages, and toggle it off (or double-click a filtered message) to jump to that message in full conversation context.
- **Disable search**: Pass `--no-search` (`python3 threema2html.py --no-search messages-chatname.txt > index.html`) for strictly static HTML without JavaScript.

This script expects German date formats and the user name "Ich" for the exporter.
For languages other than German, you will probably need to adjust some code.

It has been tested on Android based exports only.

Screenshot
----------

![Demo Screenshot](https://github.com/hkramski/threema2html/blob/master/demo.png "Demo Screenshot")
