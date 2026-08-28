import time
import random


class GeminiManager:
    def __init__(self, api_keys, models):
        self._keys = list(api_keys)
        self._models = list(models)
        self._cooldowns = {}

    def _get_active_keys(self):
        now = time.time()
        expired = [k for k, exp in list(self._cooldowns.items()) if now >= exp]
        for k in expired:
            del self._cooldowns[k]
        active = [k for k in self._keys if k not in self._cooldowns]
        random.shuffle(active)
        return active

    def _cooldown_key(self, key, seconds=15):
        self._cooldowns[key] = time.time() + seconds

    def _wait_for_cooldown(self):
        if not self._cooldowns:
            return
        earliest = min(self._cooldowns.values())
        wait = max(0, earliest - time.time())
        if wait > 0:
            time.sleep(wait + 1.0)

    def generate_content(self, contents, model=None, forced_key=None):
        from google import genai
        models_to_try = [model] + [m for m in self._models if m != model] if model else list(self._models)
        last_error = None

        for mn in models_to_try:
            active = self._get_active_keys()
            key_order = []
            if forced_key and forced_key in active:
                key_order.append(forced_key)
                key_order.extend(k for k in active if k != forced_key)
            else:
                key_order = active

            if not key_order:
                self._wait_for_cooldown()
                active = self._get_active_keys()
                key_order = [forced_key] if forced_key and forced_key in active else active
                if not key_order:
                    continue

            for i, ak in enumerate(key_order):
                if i > 0:
                    time.sleep(random.uniform(1.5, 2.0))

                for attempt in range(3):
                    try:
                        c = genai.Client(api_key=ak)
                        resp = c.models.generate_content(model=mn, contents=contents)
                        tok = {"prompt": 0, "output": 0, "total": 0}
                        um = getattr(resp, "usage_metadata", None)
                        if um:
                            tok["prompt"] = getattr(um, "prompt_token_count", 0) or 0
                            tok["output"] = getattr(um, "candidates_token_count", 0) or 0
                            tok["total"] = getattr(um, "total_token_count", 0) or 0
                        return resp, mn, ak, tok
                    except Exception as e:
                        last_error = e
                        estr = str(e)
                        is_429 = any(x in estr for x in ["429", "RESOURCE_EXHAUSTED", "Rate Limit"])
                        is_503 = "503" in estr
                        is_403 = any(x in estr for x in ["403", "PERMISSION_DENIED"])

                        if is_429:
                            print(f"⏳ [GEMINI] {mn} / {ak[:12]}... 429 RATE LIMIT, key 15sn soguyor...")
                            self._cooldown_key(ak, 15)
                            break
                        elif is_503 and attempt < 2:
                            print(f"⏳ [GEMINI] {mn} / {ak[:12]}... 503, {attempt+1}/3 deneme, 5sn bekleniyor...")
                            time.sleep(5)
                        elif is_403:
                            print(f"⚠️ [GEMINI] {mn} / {ak[:12]}... 403 PERMISSION_DENIED, key atlaniyor: {e}")
                            break
                        else:
                            print(f"⚠️ [GEMINI] {mn} / {ak[:12]}... basarisiz: {e}")
                            break

        raise Exception("Tum Gemini modelleri ve API key'leri denendi, basarisiz") from last_error
