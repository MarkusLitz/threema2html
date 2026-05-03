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
   Note: Referenced media files will be automatically copied to the `./media/` folder if they are found in the same directory as the input file.
6. Adjust `./lib/default.css`.

This script expects German date formats and the user name "Ich" for the exporter.
For languages other than German, you will probably need to adjust some code.

It has been tested on Android based exports only.

Screenshot
----------

![Demo Screenshot](https://github.com/hkramski/threema2html/blob/master/demo.png "Demo Screenshot")
