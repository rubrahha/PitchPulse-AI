'use strict';
/* PitchPulse AI v1.3: local-first, text-first, progressive-enhancement voice.
 * No third-party JS, analytics or remote assets. Avoid exposing API keys. */
const $ = id => document.getElementById(id);
const state = {
  sport:'all', matchSport:'cricket', history:[], busy:false, abortChat:null,
  muted:false, speaking:false, listening:false, recognition:null, recognizerBlocked:false,
  sttReady:false, sttProvider:'none', recording:false, recorder:null, stream:null,
  recordTimer:null, cancelRecording:false, requestingMic:false, micTestRunning:false,
  newsLoaded:false, matchesLoaded:false, panelOpen:false
};
const node = (tag, className='', text='') => {
  const el=document.createElement(tag);if(className)el.className=className;
  if(text!==undefined&&text!==null)el.textContent=text;return el;
};
const formatTime = (iso, fallback='Time unverified') => {
  if(!iso)return fallback;const d=new Date(iso);if(!Number.isFinite(d.getTime()))return fallback;
  return new Intl.DateTimeFormat('en-IN',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'}).format(d)+' IST';
};
const timeAgo = iso => {
  const v=new Date(iso||'').valueOf();if(!Number.isFinite(v))return 'Date unverified';
  const mins=Math.floor((Date.now()-v)/60000);
  if(mins>=0&&mins<2)return 'Just published';if(mins>=2&&mins<60)return `${mins}m ago`;
  if(mins>=60&&mins<1440)return `${Math.floor(mins/60)}h ago`;return formatTime(iso);
};
async function api(path,options={}){
  const controller=new AbortController();const outside=options.signal;
  const abort=()=>controller.abort();outside?.addEventListener('abort',abort,{once:true});
  if(outside?.aborted)controller.abort();
  const timer=setTimeout(abort,path.startsWith('/api/transcribe')?150000:50000);
  try{
    const res=await fetch(path,{...options,signal:controller.signal});
    if(!res.ok){let detail=`Request failed (${res.status})`;
      try{const json=await res.json();if(typeof json.detail==='string')detail=json.detail;}catch(_){/* safe fallback */}
      throw new Error(detail);
    }
    return await res.json();
  }finally{clearTimeout(timer);outside?.removeEventListener('abort',abort);}
}
function setStatus(text,kind='normal'){
  $('statusLabel').textContent=text;
  $('statusLabel').dataset.kind=kind;
}
function warning(text){$('micWarning').textContent=text;$('micWarning').hidden=!text;}
function setLive(text,active){$('voiceLive').hidden=!active;$('voiceLiveText').textContent=text||'Listening…';$('micButton').classList.toggle('active',active);$('micButton').setAttribute('aria-label',active?'Stop voice question':'Start voice question');}
function focusInput(){try{$('chatInput').focus({preventScroll:true});}catch(_){$('chatInput').focus();}}
function resizeInput(){const t=$('chatInput');t.style.height='auto';t.style.height=Math.min(156,Math.max(58,t.scrollHeight))+'px';}
function fillInput(text){$('chatInput').value=text;resizeInput();focusInput();}
function scrollToLatest(){$('chatScroll').scrollTop=$('chatScroll').scrollHeight;}
function showEmpty(target,title,message,href){target.replaceChildren();const container=node('div','empty-state');
  container.append(node('strong','',title),node('span','',message));
  if(href){const link=node('a','','Get provider access ↗');link.href=href;link.target='_blank';link.rel='noopener noreferrer';container.append(link);}
  target.append(container);
}
async function loadHealth(){
  try{
    const h=await api('/api/health');state.sttReady=!!h.stt_ready;state.sttProvider=h.stt_backend||'none';
    const active=!!h.llm_ready;const name=active?(h.llm_provider==='ollama'?'Ollama AI':'OpenAI configured'):'News reader mode';
    $('modelStatus').lastChild.textContent=' '+name;$('modelStatus').classList.add('ready');$('modelStatus').classList.remove('offline');
    $('sidebarMode').textContent=active?`AI: ${name}`:'To enable AI reasoning, add an OpenAI key or run Ollama';
    $('modelStatus').title=active?'Model configured; availability verified when you ask a question':'Without an LLM, answers are limited to verified news headlines';
  }catch(_){$('modelStatus').lastChild.textContent=' Server offline';$('modelStatus').classList.add('offline');setStatus('Backend unavailable','error');}
}
async function loadNews(){
  $('newsList').replaceChildren(node('div','loading-lines','Loading source-linked headlines…'));
  try{
    const r=await api('/api/news?sport='+encodeURIComponent(state.sport)+'&limit=10');state.newsLoaded=true;
    $('newsList').replaceChildren();
    if(!r.items?.length){showEmpty($('newsList'),'No headlines available','News feeds have not returned any articles.');}
    else for(const item of r.items.slice(0,8)){
      if(!/^https:\/\//i.test(item.url||''))continue;
      const link=node('a','news-item');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      link.append(node('span','news-title',item.title||'Untitled story'),node('span','news-meta',`${item.source||'Source'} · ${timeAgo(item.published)}`));$('newsList').append(link);
    }
    $('newsFoot').textContent=(r.stale?'CACHED · ':'')+(r.errors?.length?'Some feeds unavailable · ':'')+'Checked '+formatTime(r.updated_at,'recently');
  }catch(err){showEmpty($('newsList'),'News unavailable',err.message);$('newsFoot').textContent='Could not verify news';}
}
function scoreText(match){
  if(Array.isArray(match.score)&&match.score.length)return match.score.slice(0,2).map(s=>`${s.r??'?'} / ${s.w??'?'} (${s.o??'?'} ov)`).join(' · ');
  if(match.home_goals!=null&&match.away_goals!=null)return `${match.home_goals}–${match.away_goals}`;
  return 'Score pending';
}
async function loadMatches(){
  $('matchList').replaceChildren(node('div','loading-lines','Loading provider match data…'));
  try{
    const r=await api('/api/matches?sport='+state.matchSport);state.matchesLoaded=true;
    if(!r.configured){showEmpty($('matchList'),'Scores not connected',`Add ${state.matchSport==='cricket'?'CRICKET_API_KEY':'FOOTBALL_API_KEY'} in .env. No fake match data is shown.`,state.matchSport==='cricket'?'https://cricketdata.org/live-cricket-score-api/':'https://www.football-data.org/');}
    else if(!r.items?.length)showEmpty($('matchList'),'No matches returned','The provider did not return matches in its current window.');
    else{
      $('matchList').replaceChildren();
      for(const m of r.items.slice(0,5)){
        const card=node('div','match-card');const top=node('div','match-row-top');
        top.append(node('span','',m.format||m.competition||'MATCH'),node('span',m.live?'live-tag':'',m.live?'● LIVE':m.date||'SCHEDULED'));
        const mid=node('div','match-row-middle');mid.append(node('span','match-name',m.name||'Match'),node('span','match-score',scoreText(m)));
        card.append(top,mid,node('div','match-row-bottom',m.status||'Status unverified'));$('matchList').append(card);
      }
    }
    $('matchFoot').textContent=(r.source||'Match provider')+(r.stale?' · Delayed/cached':' · Provider-reported');$('matchUpdated').textContent=formatTime(r.updated_at,'');
  }catch(err){showEmpty($('matchList'),'Match feed unavailable',err.message);$('matchFoot').textContent='Cannot verify current scores';}
}
function openPanel(open){state.panelOpen=open;$('explorePanel').hidden=!open;$('sourcesToggle').setAttribute('aria-expanded',String(open));
  if(open){if(!state.newsLoaded)void loadNews();if(!state.matchesLoaded)void loadMatches();}
}
function switchSport(s){state.sport=s;document.querySelectorAll('[data-sport]').forEach(e=>e.classList.toggle('active',e.dataset.sport===s));
  if(state.panelOpen)void loadNews();if(s!=='all'&&s!==state.matchSport){state.matchSport=s;state.matchesLoaded=false;document.querySelectorAll('[data-matchsport]').forEach(e=>e.classList.toggle('active',e.dataset.matchsport===s));if(state.panelOpen)void loadMatches();}
  $('layout').classList.remove('nav-open');setStatus('Sport focus: '+(s==='all'?'all sports':s));
}
function stopSpeech(){if('speechSynthesis' in window){try{window.speechSynthesis.cancel();}catch(_){}}state.speaking=false;}
function speak(text){if(state.muted||!('speechSynthesis' in window)||!window.SpeechSynthesisUtterance)return;
  stopSpeech();const content=String(text||'').replace(/https?:\/\/\S+/g,'').slice(0,1600);
  if(!content)return;
  const utterance=new SpeechSynthesisUtterance(content);utterance.lang=$('langSelect').value;utterance.rate=1;utterance.pitch=1;
  const voices=window.speechSynthesis.getVoices?.()||[];utterance.voice=voices.find(v=>v.lang===utterance.lang)||voices.find(v=>v.lang.startsWith(utterance.lang.split('-')[0]))||null;
  utterance.onstart=()=>{state.speaking=true;};utterance.onend=()=>{state.speaking=false;};utterance.onerror=()=>{state.speaking=false;};
  try{window.speechSynthesis.speak(utterance);}catch(_){setStatus('Voice playback unavailable','error');}
}
function cancelRecording(){
  state.cancelRecording=true;clearTimeout(state.recordTimer);
  if(state.recorder && state.recorder.state!=='inactive')try{state.recorder.stop();}catch(_){}
  if(state.stream)state.stream.getTracks().forEach(track=>track.stop());
  state.recording=false;state.recorder=null;state.stream=null;
}
function stopListening(){
  if(state.recognition)try{state.recognition.abort();}catch(_){}
  state.recognition=null;state.listening=false;cancelRecording();setLive('',false);
}
function stopRecording(){clearTimeout(state.recordTimer);if(state.recorder&&state.recorder.state==='recording')state.recorder.stop();}
function voiceTranscript(text){
  if(!text?.trim()){warning('No speech was detected. Please try again.');setStatus('No speech detected','error');return;}
  warning('');fillInput(text.trim());setStatus($('autoSendVoice').checked?'Voice received, sending…':'Voice captured — review it, then press Send');
  if($('autoSendVoice').checked)queueMicrotask(()=>void sendMessage(text.trim()));
}
async function testMicrophone(){
  if(state.micTestRunning||state.requestingMic)return;
  if(!navigator.mediaDevices?.getUserMedia){warning('Microphone capture is unavailable. Use Chrome/Edge at http://127.0.0.1:8000');return;}
  state.micTestRunning=true;$('micTestButton').disabled=true;
  try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});const available=stream.getAudioTracks().length>0;
    stream.getTracks().forEach(t=>t.stop());if(!available)throw Object.assign(new Error('No audio input'),{name:'NotFoundError'});
    warning(state.recognizerBlocked? 'Microphone hardware is working, but the browser speech service is refusing recognition. Use backup recording if configured.' : 'Microphone hardware is working. Click Voice to ask a question.');
    setStatus('Microphone test passed');
  }catch(err){const kind=err?.name;warning(kind==='NotAllowedError'?'Chrome/Windows denied microphone capture. Check site and Windows microphone permissions.':kind==='NotReadableError'?'Microphone is in use or unavailable. Check Windows Sound settings.':kind==='NotFoundError'?'No microphone found. Check Windows Sound → Input.':`Microphone test failed: ${String(kind||err.message).slice(0,90)}`);setStatus('Microphone test failed','error');}
  finally{state.micTestRunning=false;$('micTestButton').disabled=false;}
}
async function startRecording(){
  if(state.requestingMic||state.recording||state.busy)return;
  if(!state.sttReady){warning('Backup recording needs OpenAI transcription or offline faster-whisper. Add an API key in .env or run setup_offline_voice.cmd.');return;}
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){warning('This browser cannot record audio. Use current Chrome or Edge.');return;}
  state.requestingMic=true;
  try{
    stopSpeech();const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
    const mime=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4'].find(s=>MediaRecorder.isTypeSupported(s));
    const recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);const chunks=[];
    state.stream=stream;state.recorder=recorder;state.cancelRecording=false;
    recorder.ondataavailable=e=>{if(e.data?.size)chunks.push(e.data);};
    recorder.onerror=()=>{warning('Audio recording failed. Check your microphone.');setStatus('Recording failed','error');};
    recorder.onstop=async()=>{
      clearTimeout(state.recordTimer);stream.getTracks().forEach(t=>t.stop());const canceled=state.cancelRecording;
      state.recorder=null;state.stream=null;state.recording=false;setLive('',false);
      if(canceled)return;
      const kind=(recorder.mimeType||'audio/webm').split(';')[0];
      const blob=new Blob(chunks,{type:kind});if(blob.size<300){warning('No audio was captured; speak for a few seconds and retry.');return;}
      const data=new FormData();data.append('audio',blob,'speech.'+(kind==='audio/mp4'?'mp4':kind==='audio/ogg'?'ogg':'webm'));
      state.busy=true;updateBusyUI();setStatus('Transcribing recorded voice…');
      try{const r=await api('/api/transcribe?language='+encodeURIComponent($('langSelect').value),{method:'POST',body:data});
        state.busy=false;updateBusyUI();voiceTranscript(r.text);}
      catch(err){warning('Backup transcription failed: '+err.message);setStatus('Transcription unavailable','error');}
      finally{state.busy=false;updateBusyUI();}
    };
    recorder.start(250);state.recording=true;warning('');setLive('Recording… tap Voice again to transcribe (max 20 seconds).',true);
    setStatus('Recording (backup transcription)');state.recordTimer=setTimeout(stopRecording,20000);
  }catch(err){warning(err?.name==='NotAllowedError'?'Microphone permission denied by browser or Windows. Run Test mic.':`Could not record microphone: ${String(err?.name||'unknown')}`);setStatus('Voice capture failed','error');}
  finally{state.requestingMic=false;}
}
function startListening(){
  if(state.busy||state.requestingMic)return;
  if(state.recording){stopRecording();return;}
  if(state.listening){stopListening();setStatus('Voice listening stopped');return;}
  stopSpeech();warning('');const Engine=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(state.recognizerBlocked||!Engine){if(state.sttReady){void startRecording();}else{warning('Browser speech recognition is unavailable. Use Test mic, or configure OpenAI/offline transcription and click Voice again.');setStatus('Voice service not configured','error');}return;}
  let recognized='';let completed=false;
  const r=new Engine();state.recognition=r;r.lang=$('langSelect').value;r.continuous=false;r.interimResults=true;r.maxAlternatives=1;
  r.onstart=()=>{state.listening=true;setLive('Listening… speak naturally.',true);setStatus('Listening to your question');};
  r.onresult=e=>{
    let text='';let final=false;
    for(let i=0;i<e.results.length;i++){text+=e.results[i][0]?.transcript||'';if(e.results[i].isFinal)final=true;}
    recognized=text.trim();setLive(recognized||'Listening…',true);
    if(final&&!completed){completed=true;state.listening=false;state.recognition=null;try{r.stop();}catch(_){}setLive('',false);voiceTranscript(recognized);}
  };
  r.onerror=e=>{
    if(e.error==='aborted'&&(!state.listening||completed))return;
    const err=e.error;
    if(err==='not-allowed'||err==='service-not-allowed'||err==='network'){state.recognizerBlocked=true;
      warning(state.sttReady?`Browser speech service refused (${err}). Your mic may still work. Tap Voice again to use recording transcription.`:`Browser speech service refused (${err}). Test mic and configure backup transcription for voice access.`);
    }else if(err==='no-speech'){warning('No words heard. Try speaking more clearly or using text.');}
    else if(err==='audio-capture'){warning('Unable to capture microphone. Click Test mic.');}
    else warning('Voice recognition problem: '+String(err||'unknown'));
    setStatus('Voice recognition stopped','error');
  };
  r.onend=()=>{state.listening=false;if(state.recognition===r)state.recognition=null;setLive('',false);};
  try{r.start();}catch(_){state.recognizerBlocked=true;warning('The browser speech service could not start. Click Voice again for backup recording if available.');setStatus('Speech service not available','error');}
}
function renderMessage(role,text,sources=[],mode='',pending=false){
  const wrap=node('article','message '+(role==='user'?'user-message':'ai-message')+(pending?' thinking':''));
  const avatar=node('span','msg-avatar','✦');const body=node('div','msg-body');
  if(role!=='user')body.append(node('span','msg-author','PitchPulse AI'));
  const paragraph=node('p','msg-copy',text);body.append(paragraph);
  if(role==='assistant'&&!pending){
    if(Array.isArray(sources)&&sources.length){const links=node('div','source-wrap');for(const s of sources.slice(0,6)){
      if(!/^https:\/\//i.test(s?.url||''))continue;
      const link=node('a','source-link',(s.source||'Source')+' ↗');link.href=s.url;link.rel='noopener noreferrer';link.target='_blank';link.title=s.title||'Open source';links.append(link);
    }if(links.children.length)body.append(links);}
    if(mode==='news_reader')body.append(node('span','message-meta','Headline reader · Configure an LLM for deeper sports questions'));
    if(mode==='fallback')body.append(node('span','message-meta','AI provider unreachable · Showing headline fallback'));
    const controls=node('div','msg-controls');const copy=node('button','msg-small','Copy');copy.type='button';copy.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(text);copy.textContent='Copied';}catch(_){setStatus('Clipboard unavailable','error');}});
    const read=node('button','msg-small','Listen');read.type='button';read.addEventListener('click',()=>speak(text));
    controls.append(copy,read);body.append(controls);
  }
  if(role==='user')wrap.append(body);else wrap.append(avatar,body);
  $('conversation').append(wrap);$('welcome').hidden=true;scrollToLatest();return wrap;
}
function updateBusyUI(){
  $('sendButton').textContent=state.busy?'■':'↑';$('sendButton').title=state.busy?'Cancel current answer':'Send question';
  $('sendButton').setAttribute('aria-label',state.busy?'Cancel answer':'Send message');
  $('micButton').disabled=state.busy;
}
async function sendMessage(raw){
  const text=String(raw||'').trim();if(!text||state.busy)return;
  if(text.length>750){warning('Maximum 750 characters per question.');return;}
  stopListening();stopSpeech();warning('');state.busy=true;updateBusyUI();
  fillInput('');renderMessage('user',text);const pending=renderMessage('assistant','Checking sports information…',[],'',true);
  setStatus('Thinking about your sports question…');const ctrl=new AbortController();state.abortChat=ctrl;
  try{
    const r=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,sport:state.sport,language:$('langSelect').value,history:state.history.slice(-6)}),signal:ctrl.signal});
    pending.remove();renderMessage('assistant',String(r.answer||'No response provided.'),r.sources||[],r.mode||'');
    state.history.push({role:'user',content:text},{role:'assistant',content:String(r.answer||'').slice(0,700)});state.history=state.history.slice(-6);
    setStatus(r.mode==='ai'?'AI answered · sources shown when available':r.mode==='fallback'?'Provider fallback · check sources':'News reader response');
    speak(r.answer||'');
  }catch(err){pending.remove();if(ctrl.signal.aborted){setStatus('Answer cancelled');}else{
    renderMessage('assistant',`I couldn't complete that request. ${err.message} Please retry.`);setStatus('Could not reach sports assistant','error');}}
  finally{state.abortChat=null;state.busy=false;updateBusyUI();scrollToLatest();}
}
function newChat(){
  if(state.abortChat)state.abortChat.abort();stopListening();stopSpeech();state.history=[];
  $('conversation').replaceChildren();$('welcome').hidden=false;fillInput('');warning('');setStatus('New conversation · ready to chat');$('layout').classList.remove('nav-open');
}
function init(){
  void loadHealth();
  document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{void sendMessage(b.dataset.prompt);$('layout').classList.remove('nav-open');}));
  document.querySelectorAll('[data-sport]').forEach(b=>b.addEventListener('click',()=>switchSport(b.dataset.sport)));
  document.querySelectorAll('[data-matchsport]').forEach(b=>b.addEventListener('click',()=>{state.matchSport=b.dataset.matchsport;document.querySelectorAll('[data-matchsport]').forEach(e=>e.classList.toggle('active',e===b));void loadMatches();}));
  $('chatForm').addEventListener('submit',e=>{e.preventDefault();if(state.busy&&state.abortChat)state.abortChat.abort();else void sendMessage($('chatInput').value);});
  $('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(state.busy&&state.abortChat)state.abortChat.abort();else void sendMessage($('chatInput').value);}});
  $('chatInput').addEventListener('input',resizeInput);
  $('micButton').addEventListener('click',startListening);
  $('cancelVoice').addEventListener('click',()=>{stopListening();setStatus('Voice cancelled');});
  $('micTestButton').addEventListener('click',()=>void testMicrophone());
  $('langSelect').addEventListener('change',()=>{stopListening();stopSpeech();setStatus('Language updated');});
  $('soundToggle').addEventListener('click',()=>{state.muted=!state.muted;if(state.muted)stopSpeech();$('soundToggle').classList.toggle('active',!state.muted);$('soundToggle').setAttribute('aria-pressed',String(!state.muted));$('soundToggle').innerHTML=state.muted?'🔇 <span>Muted</span>':'🔊 <span>Read aloud</span>';setStatus(state.muted?'Voice replies muted':'Voice replies enabled');});
  $('stopSpeaking').addEventListener('click',()=>{stopSpeech();setStatus('Audio stopped');});
  $('newChat').addEventListener('click',newChat);
  $('sourcesToggle').addEventListener('click',()=>openPanel(!state.panelOpen));$('closeExplore').addEventListener('click',()=>openPanel(false));$('refreshNews').addEventListener('click',()=>void loadNews());
  $('openSidebar').addEventListener('click',()=>$('layout').classList.add('nav-open'));
  $('closeSidebar').addEventListener('click',()=>$('layout').classList.remove('nav-open'));
  $('scrim').addEventListener('click',()=>$('layout').classList.remove('nav-open'));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(state.listening||state.recording)stopListening();else if(state.panelOpen)openPanel(false);else $('layout').classList.remove('nav-open');}});
  if(!(window.SpeechRecognition||window.webkitSpeechRecognition))setStatus('Text ready · Browser voice requires backup transcription');
  // Only refresh while the user is viewing the sports panel; avoid provider quota waste.
  setInterval(()=>{if(document.visibilityState==='visible'&&state.panelOpen){void loadNews();void loadMatches();}},5*60*1000);
  resizeInput();
}
document.addEventListener('DOMContentLoaded',init);
