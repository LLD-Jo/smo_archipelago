"""SMO Archipelago client package.

Lives inside the apworld so it ships in the .apworld zip and is auto-
discovered by Archipelago's Launcher (see ../__init__.py for the
Component registration). Kept deliberately empty so importing this
package does NOT pull Kivy or any Launcher/UI machinery — the apworld's
__init__ is also imported at AP generation time on headless hosts that
have no display server.
"""

__version__ = "0.1.0"
