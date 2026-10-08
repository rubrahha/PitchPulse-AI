"""Simulated LLM service contracts for genuine sports queries.

No external AI model is called here: local MockTransport validates prompt context
and provider selection while returning representative mock model replies.
"""
import json
from dataclasses import replace
import httpx
import pytest
from sportpulse.brain import answer, detect_sport, is_score_question, is_timely_question
from sportpulse.config import Settings


class SportsFixtures:
    def __init__(self):
        self.news_calls = []
        self.score_calls = []

    async def news(self, sport, query='', limit=20):
        self.news_calls.append((sport, query))
        news = (
            {'title': 'India squad announcement', 'summary': 'Team released a squad list',
             'url': 'https://bbc.co.uk/cricket', 'published': '2026-10-08T08:00:00Z', 'source': 'BBC Sport'}
            if sport == 'cricket' else
            {'title': 'Premier League fixture update', 'summary': 'Fixtures published',
             'url': 'https://bbc.co.uk/football', 'published': '2026-10-08T08:00:00Z', 'source': 'BBC Sport'}
        )
        return {'items': [news], 'errors': []}

    async def cricket(self):
        self.score_calls.append('cricket')
        return {'configured': True, 'source': 'Test fixture', 'items': [
            {'name': 'India vs Australia', 'status': 'Australia won',
             'score': [{'inning':'India', 'r':100, 'w':5, 'o':20}]}]}

    async def football(self):
        self.score_calls.append('football')
        return {'configured': True, 'source': 'Test fixture', 'items': [
            {'name': 'Arsenal vs Chelsea', 'status': 'FINISHED',
             'home_goals': 2, 'away_goals': 1}]}


@pytest.mark.parametrize('question,sport,kind', [
    ('Explain DRS in cricket to a beginner', 'cricket', 'knowledge'),
    ('Explain the offside rule in football', 'football', 'knowledge'),
    ('Compare a cricket captain and a football manager', 'all', 'knowledge'),
    ('How many overs are in a T20 match?', 'cricket', 'knowledge'),
    ('Give me the latest cricket news', 'cricket', 'news'),
    ('What is new in football today?', 'football', 'news'),
    ('What are the latest cricket scores?', 'cricket', 'score'),
    ('What is the score of Arsenal vs Chelsea today?', 'football', 'score'),
    ('Who won India vs Pakistan today?', 'all', 'score'),
    ('What is a goal in football?', 'football', 'knowledge'),
])
@pytest.mark.asyncio
async def test_llm_sports_questions_use_correct_grounding(question, sport, kind):
    fixtures = SportsFixtures()
    calls = []

    def handler(req):
        assert req.url.path == '/v1/responses'
        body = json.loads(req.content)
        assert body['store'] is False  # don't store on provider
        assert 'Current sports stories' in body['instructions']
        assert 'USER QUESTION: ' + question in body['input'][-1]['content']
        context = body['input'][-1]['content'].split('SOURCE DATA: ', 1)[1]
        payload = json.loads(context)
        calls.append(payload)
        if kind == 'knowledge':
            assert payload['news'] == []
            assert payload['scores'] == []
            reply = 'Here is a simple explanation, followed by a sports example.'
        elif kind == 'news':
            assert payload['news']
            assert not payload['scores']
            reply = 'Here is the latest provider headline, with the source linked below.'
        else:
            assert isinstance(payload['scores'], list)
            # No India vs Pakistan match exists in mocked provider fixtures.
            if 'India vs Pakistan' in question:
                assert payload['scores'] == []
            reply = 'I can only report scores verified in the supplied provider data.'
        return httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':reply}]}]})

    model=replace(Settings(),llm_provider='openai',openai_api_key='mock-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out=await answer(question, detect_sport(question), 'en-IN',[],fixtures,model,client)
    assert out['mode']=='ai'
    assert calls
    if kind=='knowledge':
        assert not fixtures.news_calls and not fixtures.score_calls
    if kind=='news':
        assert fixtures.news_calls and not fixtures.score_calls
    if kind=='score':
        assert fixtures.score_calls


@pytest.mark.asyncio
async def test_llm_followup_history_and_hinglish_language():
    record = []
    def handler(req):
        data=json.loads(req.content)
        record.extend(data['input'])
        return httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':'DRS umpire ke decision ko review karne mein madad karta hai.'}]}]})
    src=SportsFixtures()
    messages=[{'role':'user','content':'Explain DRS in cricket'},
              {'role':'assistant','content':'DRS helps review decisions.'}]
    model=replace(Settings(),llm_provider='openai',openai_api_key='mock-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out=await answer('Explain it in simple Hinglish','cricket','hi-IN',messages,src,model,client)
    assert [x['role'] for x in record]==['user','assistant','user']
    assert 'LANGUAGE: hi-IN' in record[-1]['content']
    assert out['mode']=='ai'


def test_live_vs_timeless_question_detection():
    assert is_score_question('What is the score?')
    assert is_score_question('Who won India vs Pakistan?')
    assert not is_score_question('How many overs are in a T20 match?')
    assert not is_score_question('What is a goal in football?')
    assert not is_timely_question('Explain offside in football')
    assert is_timely_question('latest football news')
