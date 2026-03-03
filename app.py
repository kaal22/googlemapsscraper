"""
Google Maps Scraper — Web UI
=============================
Flask web app wrapper for the Google Maps scraper.
Provides a dashboard to configure, run, and view scrape results.

Usage:
    python app.py
    → Opens at http://localhost:5000
"""

import os
import csv
import json
import threading
import queue
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, send_file
from scraper import scrape_google_maps, save_to_csv, sanitize_filename, RESULTS_DIR, DEFAULTS

app = Flask(__name__)

# Track active scrape jobs
active_jobs = {}


class ScrapeJob:
    """Represents a running scrape job with progress tracking."""
    def __init__(self, query, config):
        self.query = query
        self.config = config
        self.status = 'starting'
        self.progress_queue = queue.Queue()
        self.results = []
        self.filename = ''
        self.error = None
        self.started_at = datetime.now()
        self.finished_at = None
        self.thread = None

    def emit(self, event, data):
        self.progress_queue.put({'event': event, 'data': data})

    def run(self):
        try:
            self.status = 'scraping'
            self.emit('status', 'Starting scrape...')

            self.results = scrape_google_maps(
                self.query,
                self.config,
                progress_callback=self.emit
            )

            if self.results:
                self.filename = sanitize_filename(self.query)
                filepath = save_to_csv(self.results, self.filename)
                emails_found = sum(1 for r in self.results if r.get('email'))
                self.emit('complete', json.dumps({
                    'total': len(self.results),
                    'emails': emails_found,
                    'filename': self.filename,
                    'filepath': filepath,
                }))
                self.status = 'complete'
            else:
                self.emit('error', 'No results found.')
                self.status = 'error'
                self.error = 'No results found'

        except Exception as e:
            self.emit('error', str(e))
            self.status = 'error'
            self.error = str(e)
        finally:
            self.finished_at = datetime.now()
            self.emit('done', '')


@app.route('/')
def index():
    return render_template('index.html', defaults=DEFAULTS)


@app.route('/start', methods=['POST'])
def start_scrape():
    """Start a new scrape job."""
    data = request.json
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'No search query provided'}), 400

    # Build config from form data
    config = {
        'max_scrolls': int(data.get('max_scrolls', DEFAULTS['max_scrolls'])),
        'scroll_pause': float(data.get('scroll_pause', DEFAULTS['scroll_pause'])),
        'action_delay_min': float(data.get('action_delay_min', DEFAULTS['action_delay_min'])),
        'action_delay_max': float(data.get('action_delay_max', DEFAULTS['action_delay_max'])),
        'timeout': int(data.get('timeout', DEFAULTS['timeout'])),
        'scrape_emails': data.get('scrape_emails', True),
        'email_timeout': int(data.get('email_timeout', DEFAULTS['email_timeout'])),
        'headless': data.get('headless', True),
    }

    # Create job
    job_id = str(int(time.time() * 1000))
    job = ScrapeJob(query, config)
    active_jobs[job_id] = job

    # Run in background thread
    thread = threading.Thread(target=job.run, daemon=True)
    job.thread = thread
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/progress/<job_id>')
def progress(job_id):
    """SSE endpoint for live progress updates."""
    def generate():
        job = active_jobs.get(job_id)
        if not job:
            yield f"data: {json.dumps({'event': 'error', 'data': 'Job not found'})}\n\n"
            return

        while True:
            try:
                msg = job.progress_queue.get(timeout=1)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg['event'] == 'done':
                    break
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
                if job.status in ('complete', 'error'):
                    break

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/results')
def list_results():
    """List all saved CSV result files."""
    files = []
    if os.path.exists(RESULTS_DIR):
        for f in sorted(os.listdir(RESULTS_DIR), reverse=True):
            if f.endswith('.csv'):
                filepath = os.path.join(RESULTS_DIR, f)
                stat = os.stat(filepath)

                # Count rows
                row_count = 0
                try:
                    with open(filepath, 'r', encoding='utf-8') as csvfile:
                        reader = csv.reader(csvfile)
                        next(reader, None)  # skip header
                        row_count = sum(1 for _ in reader)
                except Exception:
                    pass

                files.append({
                    'name': f,
                    'size': f"{stat.st_size / 1024:.1f} KB",
                    'rows': row_count,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                })
    return jsonify(files)


@app.route('/results/<filename>')
def get_result(filename):
    """Get contents of a result CSV as JSON."""
    filepath = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    rows = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return jsonify(rows)


@app.route('/download/<filename>')
def download_result(filename):
    """Download a result CSV file."""
    filepath = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route('/delete/<filename>', methods=['DELETE'])
def delete_result(filename):
    """Delete a result CSV file."""
    filepath = os.path.join(RESULTS_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'success': True})
    return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  Google Maps Scraper — Web UI")
    print("  Open: http://localhost:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000, threaded=True)
