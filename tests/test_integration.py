"""Offline provider contract tests; never contact real sports or LLM APIs."""
import httpx
import pytest
from sportpulse.config import Settings
from sportpulse.providers import SportsSources
from sportpulse.brain import answer


@pytest.mark.asyncio
async def test_cricket_provider_contract():
    def handler(request):
        assert request.url.host == 'api.cricapi.com'
        assert request.url.params['apikey'] == 'mock-key'
        return httpx.Response(200,json={'status':'success','data':[
            {'id':'1','name':'India vs Australia','matchType':'t20','status':'India need 10 runs',
             'matchStarted':True,'matchEnded':False,
             'score':[{'inning':'India Inning 1','r':150,'w':4,'o':18.2}]}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        from dataclasses import replace
        source=SportsSources(replace(Settings(),cricket_api_key='mock-key'),client)
        data=await source.cricket()
        assert data['configured'] is True
        assert data['items'][0]['live'] is True
        assert data['items'][0]['score'][0]['r']==150
        assert (await source.cricket())['cached'] is True


@pytest.mark.asyncio
async def test_football_provider_contract():
    def handler(request):
        assert request.headers['X-Auth-Token'] == 'fake-football-key'
        return httpx.Response(200,json={'matches':[{'id':123,'status':'IN_PLAY',
               'utcDate':'2026-10-08T17:00:00Z','homeTeam':{'shortName':'Arsenal'},
               'awayTeam':{'shortName':'Chelsea'},'score':{'fullTime':{'home':1,'away':0}},
               'competition':{'name':'Premier League'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        from dataclasses import replace
        source=SportsSources(replace(Settings(),football_api_key='fake-football-key'),client)
        data=await source.football()
        assert data['items'][0]['name']=='Arsenal vs Chelsea'
        assert data['items'][0]['live'] is True
        assert data['items'][0]['home_goals']==1


@pytest.mark.asyncio
async def test_news_rss_sources_offline():
    def handler(request):
        if request.url.host == 'news.google.com':
            return httpx.Response(200,text='<rss><channel><item><title>Latest cricket score update</title><link>https://news.google.com/a</link><pubDate>Thu, 08 Oct 2026 03:40:00 GMT</pubDate></item></channel></rss>')
        return httpx.Response(200,text='<rss><channel><item><title>India team selection news</title><link>https://bbc.com/news</link><pubDate>Thu, 08 Oct 2026 03:30:00 GMT</pubDate></item></channel></rss>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sources=SportsSources(Settings(),client)
        data=await sources.news('cricket','India',20)
        assert len(data['items'])==2
        assert data['items'][0]['source']=='Google News'
        assert all(item['url'].startswith('https://') for item in data['items'])


@pytest.mark.asyncio
async def test_openai_responses_contract_with_mock_sources():
    from dataclasses import replace
    from sportpulse.brain import answer
    class FakeSources:
        async def news(self, sport, query='', limit=20):
            return {'items':[{'title':'India announce squad','summary':'Squad news','url':'https://bbc.com/squad',
                              'published':'2026-10-08T02:00:00+00:00','source':'BBC Sport'}]}
    def handler(request):
        assert request.url.path=='/v1/responses'
        import json
        req=json.loads(request.content)
        assert req['store'] is False
        assert 'India announce squad' in str(req['input'])
        assert request.headers['Authorization']=='Bearer fake-openai-key'
        return httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':'BBC reports that India announced its squad.'}]}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        settings=replace(Settings(),openai_api_key='fake-openai-key',llm_provider='openai')
        result=await answer('Latest India cricket news','cricket','en-IN',[],FakeSources(),settings,client)
        assert result['mode']=='ai'
        assert 'BBC reports' in result['answer']
        assert result['sources'][0]['url']=='https://bbc.com/squad'
