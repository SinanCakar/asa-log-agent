ASA Log Agent — in-game tribe-log reader (Setup & Usage)
=========================================================

WHAT IT DOES
  Reads the ARK tribe-log panel from your own screen with OCR, classifies the
  events (raid, kill, member, tame, claim) and sends them to a Discord bot.
  It only sends genuine tribe-log lines that start with "Day N, HH:MM:SS:";
  nothing else on your screen is ever sent.
  ANTI-CHEAT SAFE: it only takes a screenshot; it never reads or touches the
  game process/memory. It runs only while you play with the log panel visible.
  Windows.

=== INSTALL (SINGLE FILE) ===
  1) Download and run ASA_LogAgent_Setup.exe.
     (Latest: github.com/SinanCakar/asa-log-agent/releases/latest)
  2) The wizard walks you through:
     - Install folder (the default is fine).
     - Components: keep "Tesseract-OCR" CHECKED (required for OCR). During
       install Tesseract opens its own window -> click Install.
     - Token: in Discord run  /log key  and paste the token.
     - Server label: e.g. "the_island 7777".
     - Bot ingest URL (HTTPS): pre-filled; change it if you self-host.
  3) Done. agent.ini is written automatically (token, server, Tesseract path).
  Note: if you do not have a token yet, run  /log key  in Discord first.

=== FIRST CALIBRATION (once) ===
  Set the screen region the agent reads the tribe-log panel from:
  1) Open ARK, bring the Tribe Manager > LOG panel on screen.
  2) Run "ASA Log Agent (Calibrate)" from the Start Menu
     (or the "calibrate now" checkbox at the end of setup).
  3) A screenshot is saved; the console prints its full path. In that image read
     the log panel's top-left corner (x, y) and its width x height.
  4) Enter those 4 numbers as  x y width height  (space separated).

=== RUN ===
  Start Menu > "ASA Log Agent".
  - Test first: in a command prompt run  ASA_LogAgent.exe --dry  -> it parses
    and prints without sending anything, so you can verify OCR.
  - If correct, run it normally -> events go to Discord.
  In Discord, pick the alert channel with  /log channel #channel
  (without it, events only show via /logs and no live alert is posted).

=== DISCORD COMMANDS ===
  /log key            generate your personal token (put it in agent.ini)
  /log channel #chan  choose the alert channel
  /log status         token / channel / rule status
  /log ruleadd        add a regex -> severity rule
  /logs [hours]       show recently captured tribe-log events

=== UPDATES ===
  On startup the agent checks GitHub for a newer release and tells you if one
  exists. Run  ASA_LogAgent.exe --update  to download and launch the latest
  installer; your existing agent.ini (token/region) is preserved.

=== SETTINGS (agent.ini) ===
  Location: same folder as the .exe.
  token, server_label, region, interval, fuzzy_threshold live here.
  Edit and save, then restart the agent.

=== UNINSTALL ===
  Settings > Apps > "ASA Log Agent" > Uninstall.
  - Asks whether to also delete your settings/data (token included).
  - Asks whether to also remove Tesseract-OCR.

=== PRIVACY ===
  Only real tribe-log lines starting with "Day N, HH:MM:SS:" are sent. Menus,
  chat and other screen text are dropped, and the same line is never re-sent.
  Never share your token (revoke with /log revoke, rotate with /log key).
