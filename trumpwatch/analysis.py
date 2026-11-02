import logging
import httpx

log=logging.getLogger(__name__)

class Analyzer:
    def __init__(self,key,model,enabled,http_client):
        self.api_key=key if enabled else ''
        self.model=model
        self.http_client=http_client
        self.last_error=''

    async def analyze(self,event):
        self.last_error=''
        if not self.api_key:
            self.last_error='Groq is not configured. Set GROQ_API_KEY and enable AI_ANALYSIS_ENABLED.'
            return ''
        prompt=f'''Explain this news item or scheduled economic event in short, simple Hinglish (Hindi written in Latin/English letters, naturally mixed with common English finance terms).
Use at most 3 brief bullet points and 70 words total. Say what happened or what the event measures, its possible relevance to USD/gold/markets, and any important uncertainty. For future events, distinguish forecast from previous values and never present a forecast as a known result.
Do not invent facts or give a trade signal.
Source={event['source']}\nTitle={event['title']}\nPublished={event['published']}\nContent={event['content'][:4500]}\nURL={event['url']}'''
        try:
            request_body={
                'model':self.model,
                'messages':[{'role':'user','content':prompt}],
                'temperature':0.2,
                'max_completion_tokens':500,
            }
            if self.model.startswith('openai/gpt-oss-'):
                request_body['reasoning_effort']='low'
            response=await self.http_client.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization':f'Bearer {self.api_key}'},
                json=request_body,
                timeout=45,
            )
            response.raise_for_status()
            result=response.json()
            choices=result.get('choices') or []
            if not choices:
                raise ValueError('Groq returned no completion choices.')
            choice=choices[0]
            message=choice.get('message') or {}
            content=message.get('content')
            if not isinstance(content,str) or not content.strip():
                if choice.get('finish_reason')=='length':
                    raise ValueError(
                        'Groq used its output limit on model reasoning before producing text. '
                        'Increase max_completion_tokens or set reasoning_effort=low.'
                    )
                raise ValueError('Groq returned an empty explanation.')
            return content.strip()
        except httpx.HTTPStatusError as exc:
            self.last_error=self._provider_error(exc.response)
        except httpx.TimeoutException:
            self.last_error='Groq request timed out. Try again shortly.'
        except httpx.RequestError as exc:
            self.last_error=f'Could not connect to Groq ({type(exc).__name__}). Check the host network and try again.'
        except (ValueError,TypeError) as exc:
            self.last_error=str(exc)[:240]
        except Exception as exc:
            self.last_error=f'Unexpected Groq client error ({type(exc).__name__}).'
        log.warning('Groq analysis failed: %s',self.last_error)
        return ''

    @staticmethod
    def _provider_error(response):
        try:
            payload=response.json()
            error=payload.get('error',{})
            detail=error.get('message','') if isinstance(error,dict) else str(error)
        except (ValueError,AttributeError):
            detail=response.text
        detail=' '.join(str(detail).split())[:240]
        status=response.status_code
        if status==401:
            return 'Groq rejected the API key (401). Check GROQ_API_KEY in .env and restart the bot.'
        if status==403:
            return f'Groq denied this request (403): {detail or "check API key permissions or account access"}'
        if status==404:
            return f'Groq could not find the configured model (404): {detail or "check GROQ_MODEL"}'
        if status==429:
            return f'Groq rate limit or quota reached (429): {detail or "try again later or check your Groq account limits"}'
        return f'Groq returned HTTP {status}: {detail or "no error details provided"}'
