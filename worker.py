#!/usr/bin/env python3
"""VidRift – vypalování vodoznaku do nových videí (běží na GitHub Actions).

Vezme nezpracované video, vypálí do něj logo VidRift + @kanál (střídá rohy každé 4 s),
nahraje výsledek zpět do B2 a řekne serveru, že je hotovo. Teprve pak video uvidí ostatní.
Tajná hodnota: WORKER_TOKEN (GitHub → Settings → Secrets and variables → Actions).
"""
import json, os, subprocess, sys, tempfile, time, urllib.request

API = os.environ.get('VIDRIFT_API', 'https://okcnditfcurqegbeshqc.supabase.co/functions/v1/b2')
TOKEN = os.environ.get('WORKER_TOKEN', '')
LOGO_URL = 'https://vidriftvideo.netlify.app/icons/icon-192.png'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
TIME_LIMIT = 20 * 60  # jedna běžící akce zpracuje videa nejvýš 20 minut, pak skončí


def api(action, **body):
    req = urllib.request.Request(API, data=json.dumps({'action': action, **body}).encode(),
                                 headers={'Content-Type': 'application/json', 'x-worker-token': TOKEN}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def download(url, path):
    with urllib.request.urlopen(url, timeout=600) as r, open(path, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def upload(url, path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        req = urllib.request.Request(url, data=f, method='PUT', headers={'Content-Type': 'video/mp4', 'Content-Length': str(size)})
        with urllib.request.urlopen(req, timeout=1800) as r:
            if r.status >= 300:
                raise RuntimeError(f'upload {r.status}')


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j['streams'][0]
    return int(s['width']), int(s['height']), float(j.get('format', {}).get('duration') or 0)


def target(w, h, short_max):
    short = min(w, h, short_max)
    if w >= h:
        nh = short; nw = round(w * short / h / 2) * 2
    else:
        nw = short; nh = round(h * short / w / 2) * 2
    return max(2, nw - nw % 2), max(2, nh - nh % 2)


def text_width(text, size):
    try:
        from PIL import ImageFont
        return round(ImageFont.truetype(FONT, size).getlength(text))
    except Exception:
        return round(size * 0.68 * len(text))


def watermark(src, dst, logo, username, short_max):
    w, h, dur = probe(src)
    tw, th = target(w, h, short_max)
    s = max(14, round(min(tw, th) * 0.045))       # velikost písma
    ls = round(s * 1.05)                            # velikost loga
    pad = round(s * 0.6)
    a = "lt(mod(t\\,8)\\,4)"                         # 0–4 s vlevo nahoře, 4–8 s vpravo dole
    b = "gte(mod(t\\,8)\\,4)"
    user = '@' + ''.join(c for c in username if c.isalnum() or c == '_')
    vw = text_width('VidRift', s)                   # šířka nápisu, aby logo sedělo i vpravo
    gap = round(s * 0.3)
    s2 = round(s * 0.62)
    txt = f"fontfile={FONT}:fontcolor=white@0.8:shadowcolor=black@0.7:shadowx=2:shadowy=2"
    # vlevo nahoře
    ly1 = pad; ty1 = pad + round((ls - s) / 2); uy1 = pad + ls + round(s * 0.2)
    # vpravo dole
    uy2 = f"h-{pad}-{s2}"; ty2 = f"h-{pad}-{s2}-{round(s * 0.35)}-{s}"; ly2 = f"H-{pad}-{s2}-{round(s * 0.35)}-{s}-{round((ls - s) / 2)}"
    fc = (
        f"[0:v]scale={tw}:{th},setsar=1[v0];"
        f"[1:v]scale={ls}:{ls},format=rgba,colorchannelmixer=aa=0.85,split[lg1][lg2];"
        f"[v0][lg1]overlay=x={pad}:y={ly1}:enable='{a}'[v1];"
        f"[v1][lg2]overlay=x=W-{pad}-{vw}-{gap}-{ls}:y={ly2}:enable='{b}'[v2];"
        f"[v2]drawtext={txt}:fontsize={s}:text='VidRift':x={pad + ls + gap}:y={ty1}:enable='{a}',"
        f"drawtext={txt}:fontsize={s2}:text='{user}':x={pad}:y={uy1}:enable='{a}',"
        f"drawtext={txt}:fontsize={s}:text='VidRift':x=w-{pad}-text_w:y={ty2}:enable='{b}',"
        f"drawtext={txt}:fontsize={s2}:text='{user}':x=w-{pad}-text_w:y={uy2}:enable='{b}'[out]"
    )
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-i', logo, '-filter_complex', fc, '-map', '[out]', '-map', '0:a?',
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
           '-c:a', 'aac', '-b:a', '128k', dst]
    subprocess.run(cmd, check=True)
    return dur


def low(src, dst):
    w, h, _ = probe(src)
    tw, th = target(w, h, 480)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-vf', f'scale={tw}:{th}', '-c:v', 'libx264', '-preset', 'veryfast',
                    '-crf', '27', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '96k', dst], check=True)


def main():
    if len(TOKEN) < 24:
        sys.exit('Chybí WORKER_TOKEN.')
    start = time.time()
    with tempfile.TemporaryDirectory() as d:
        logo = os.path.join(d, 'logo.png')
        download(LOGO_URL, logo)
        while time.time() - start < TIME_LIMIT:
            job = api('job_next').get('job')
            if not job:
                print('Žádná další videa. Hotovo.')
                return
            jid = job['id']
            print('Zpracovávám', jid)
            try:
                src, out, lo = (os.path.join(d, n) for n in ('in.bin', 'out.mp4', 'low.mp4'))
                download(job['get'], src)
                dur = watermark(src, out, logo, job['username'], 720)
                upload(job['put'], out)
                has_low = False
                if job.get('hasLow'):
                    low(out, lo); upload(job['putLow'], lo); has_low = True
                api('job_done', id=jid, low=has_low, duration_s=dur)
                print('Hotovo', jid)
            except Exception as e:  # nevyšlo → server to za 30 min zkusí znovu
                print('Chyba', jid, e)
                try: api('job_fail', id=jid, reason=str(e))
                except Exception: pass
            finally:
                for n in ('in.bin', 'out.mp4', 'low.mp4'):
                    try: os.remove(os.path.join(d, n))
                    except OSError: pass


if __name__ == '__main__':
    main()
