#!/usr/bin/env python3
"""
Web interface for Autoswagger
"""
from flask import Flask, request, jsonify, render_template_string
import subprocess
import json
import os

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Autoswagger Web Interface</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        input[type="text"] { width: 100%; padding: 10px; margin: 10px 0; }
        button { background: #007cba; color: white; padding: 10px 20px; border: none; cursor: pointer; }
        .results { background: #f5f5f5; padding: 20px; margin: 20px 0; white-space: pre-wrap; }
        .checkbox { margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Autoswagger Security Scanner</h1>
        <form id="scanForm">
            <label>Target URL:</label>
            <input type="text" id="url" placeholder="https://api.example.com" required>
            
            <div class="checkbox">
                <input type="checkbox" id="verbose"> <label for="verbose">Verbose output</label>
            </div>
            <div class="checkbox">
                <input type="checkbox" id="risk"> <label for="risk">Include risky methods (POST, PUT, DELETE)</label>
            </div>
            <div class="checkbox">
                <input type="checkbox" id="product"> <label for="product">Show only PII/secrets</label>
            </div>
            
            <button type="submit">🚀 Start Scan</button>
        </form>
        
        <div id="results" class="results" style="display:none;"></div>
    </div>

    <script>
        document.getElementById('scanForm').onsubmit = function(e) {
            e.preventDefault();
            
            const url = document.getElementById('url').value;
            const verbose = document.getElementById('verbose').checked;
            const risk = document.getElementById('risk').checked;
            const product = document.getElementById('product').checked;
            
            document.getElementById('results').style.display = 'block';
            document.getElementById('results').innerHTML = 'Scanning... Please wait...';
            
            fetch('/scan', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url, verbose, risk, product})
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('results').innerHTML = data.output || data.error;
            })
            .catch(error => {
                document.getElementById('results').innerHTML = 'Error: ' + error;
            });
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/scan', methods=['POST'])
def scan():
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Build command
        cmd = ['python', 'autoswagger.py', url, '-json']
        
        if data.get('verbose'):
            cmd.append('-v')
        if data.get('risk'):
            cmd.append('-risk')
        if data.get('product'):
            cmd.append('-product')
        
        # Execute scan
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            return jsonify({'output': result.stdout})
        else:
            return jsonify({'error': f'Scan failed: {result.stderr}'})
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Scan timed out (5 minutes limit)'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)