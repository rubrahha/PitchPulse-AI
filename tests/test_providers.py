import pytest
from sportpulse.brain import detect_sport, is_score_question, relevant_articles
from sportpulse.providers import parse_rss, clean_text, safe_link, TTLCache


def test_rss_parse_safe_data():
    feed = b'''<rss><channel><item><title>India win the test</title><link>https://example.com/news</link>
       <description>&lt;b&gt;Match report&lt;/b&gt;</description><pubDate>Thu, 08 Oct 2026 04:00:00 GMT</pubDate></item>
       <item><title>Bad link</title><link>javascript:alert(1)</link></item></channel></rss>'''
    articles = parse_rss(feed, "cricket", "Example")
    assert len(articles) == 1
    assert articles[0]["summary"] == "Match report"
    assert articles[0]["published"].startswith("2026-10-08")


def test_xml_entity_attack_rejected():
    feed = b'<!DOCTYPE lolz [<!ENTITY x "EXPANSION">]><rss><channel><item><title>&x;</title></item></channel></rss>'
    with pytest.raises(Exception):
        parse_rss(feed, "all", "Example")


def test_safe_url():
    assert safe_link('javascript:alert(1)') == ''
    assert safe_link('http://someone:password@site.com/x') == ''
    assert safe_link('https://bbc.com/x') == 'https://bbc.com/x'
    assert clean_text('<b>Hello</b>  world') == 'Hello world'


def test_sport_classification():
    assert detect_sport('Virat Kohli batting today?') == 'cricket'
    assert detect_sport('Barcelona transfer news') == 'football'
    assert detect_sport('Tell me about teams', 'cricket') == 'cricket'
    assert is_score_question('What is the live score?')
    assert not is_score_question('Explain an offside rule')


def test_relevance():
    items = [{'title':'Unrelated headline','summary':''},{'title':'Virat Kohli centuries','summary':''}]
    assert relevant_articles(items,'Tell me about Virat Kohli')[0]['title'].startswith('Virat')


@pytest.mark.asyncio
async def test_cache_dedupes_concurrent_requests():
    import asyncio
    cache=TTLCache()
    calls=0
    async def loader():
        nonlocal calls
        calls+=1
        await asyncio.sleep(.01)
        return {'items':[1]}
    results=await asyncio.gather(*(cache.get('key',60,loader) for _ in range(10)))
    assert calls==1
    assert all(result['items']==[1] for result in results)
