import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["SUPABASE_DATABASE_URL"] = ""
from django.core.management import execute_from_command_line
import sys
sys.argv = ["manage.py", "check"]
execute_from_command_line(sys.argv)
