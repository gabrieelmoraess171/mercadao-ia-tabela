import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlencode, parse_qs

import httpx
import pytest

from services.mercadolivre_auth import MercadoLivreOAuth

PAGE = Path(__file__).resolve().parents[1] / "oauth-retorno" / "retorno.html"
HTML = PAGE.read_text(encoding="utf-8")
SCRIPT = re.search(r"<script>(.*?)</script>", HTML, re.S).group(1)
NODE = shutil.which("node")

HARNESS = r"""
const vm = require('node:vm');
const fs = require('node:fs');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const copied = [], cleaned = [], elements = {};
  for (const id of ['status','retorno','copiar']) {
    elements[id] = {value:'',textContent:'',disabled:id==='copiar',handlers:{},focused:false,selected:false,
      addEventListener(event, fn){this.handlers[event]=fn;},
      focus(){this.focused=true;},select(){this.selected=true;}};
  }
  const context = {URL,
    document:{getElementById(id){return elements[id];}},
    window:{location:{href:input.href},history:{replaceState(_a,_b,path){cleaned.push(path);}}},
    navigator:{clipboard:{async writeText(value){if(input.failClipboard)throw Error('Clipboard denied');copied.push(value);}}}
  };
  vm.runInNewContext(input.source,context,{timeout:1000});
  if(elements.copiar.handlers.click)await elements.copiar.handlers.click();
  process.stdout.write(JSON.stringify({copied,cleaned,status:elements.status.textContent,
    value:elements.retorno.value,disabled:elements.copiar.disabled,selected:elements.retorno.selected}));
})().catch(() => {process.exitCode=1;});
"""


def browser(url, fail_clipboard=False):
    completed = subprocess.run([NODE, "-e", HARNESS],
        input=json.dumps({"href": url, "source": SCRIPT, "failClipboard": fail_clipboard}),
        text=True, capture_output=True, check=True, timeout=10)
    return json.loads(completed.stdout)


def test_content_security_hashes_match_and_external_assets_are_absent():
    for tag in ("script", "style"):
        body = re.search("<"+tag+r">(.*?)</"+tag+">", HTML, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert "'sha256-" + digest + "'" in HTML
    assert "default-src 'none'" in HTML and 'name="referrer" content="no-referrer"' in HTML
    assert not re.search(r"<(?:script|img)\b[^>]*\bsrc=|<link\b", HTML, re.I)
    assert 'type="password"' in HTML and 'readonly' in HTML
    assert "__SCRIPT_HASH__" not in HTML and "__STYLE_HASH__" not in HTML


@pytest.mark.skipif(not NODE, reason="Node.js é necessário apenas para exercitar o script estático nos testes")
def test_copied_callback_completes_validated_oauth_exchange():
    def handle(request):
        assert parse_qs(request.content.decode())["code"] == ["one-time-code"]
        return httpx.Response(200, json={"access_token": "test-access", "expires_in": 21600, "token_type": "bearer"})
    oauth = MercadoLivreOAuth("123456", "test-secret", "https://retorno.example.test/retorno.html",
        client=httpx.Client(transport=httpx.MockTransport(handle)))
    try:
        attempt, _ = oauth.begin()
        url = attempt.redirect_uri + "?" + urlencode({"code": "one-time-code", "state": attempt.state})
        result = browser(url)
        assert result["copied"] == [url] and result["cleaned"] == ["/retorno.html"]
        assert "one-time-code" not in result["status"] and attempt.state not in result["status"]
        assert oauth.finish(attempt, result["copied"][0]).access_token == "test-access"
    finally:
        oauth.close()


@pytest.mark.skipif(not NODE, reason="Node.js é necessário apenas para exercitar o script estático nos testes")
@pytest.mark.parametrize("url", ["https://retorno.example.test/retorno.html", "http://retorno.example.test/retorno.html?code=x&state=s",
    "https://retorno.example.test/retorno.html?code=a&code=b&state=s", "https://retorno.example.test/retorno.html?code=a&state=s#other"])
def test_invalid_page_return_is_not_copied(url):
    result = browser(url)
    assert result["disabled"] and result["copied"] == [] and result["value"] == ""


@pytest.mark.skipif(not NODE, reason="Node.js é necessário apenas para exercitar o script estático nos testes")
def test_denied_authorization_is_not_shown_as_connected():
    url = "https://retorno.example.test/retorno.html?error=access_denied&state=test-state"
    result = browser(url)
    assert "recusou ou cancelou" in result["status"] or "Retorno copiado" in result["status"]
    assert result["copied"] == [url]
    assert "conectada" not in result["status"] and "test-state" not in result["status"]


@pytest.mark.skipif(not NODE, reason="Node.js é necessário apenas para exercitar o script estático nos testes")
def test_clipboard_denial_offers_manual_copy_without_network():
    result = browser("https://retorno.example.test/retorno.html?code=test-code&state=test-state", fail_clipboard=True)
    assert result["selected"] and "Ctrl+C" in result["status"] and not result["copied"]
