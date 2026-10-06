"""
The flask application package.
"""
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
app = Flask(__name__)

import CFB_Predicition_Model.views