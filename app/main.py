from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello GitOps v1\n"

app.run(host="0.0.0.0", port=8080)
