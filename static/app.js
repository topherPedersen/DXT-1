const RD8 = {kick:36,snare:40,closed_hat:42,open_hat:46,low_tom:45,mid_tom:47,high_tom:50,cymbal:51};
let events = [], midiAccess = null, timers = [], playing = false;
const $ = id => document.getElementById(id);
function status(text, error=false){ $('status').textContent=text; $('status').className=error?'danger':''; }

$('transcribe').onclick = async () => {
  const file=$('audioFile').files[0]; if(!file) return status('Choose an audio file first.',true);
  const form=new FormData(); form.append('file',file); form.append('skip_demucs',$('skipDemucs').checked);
  form.append('device',$('device').value); form.append('thresholds',$('thresholds').value);
  status('Processing. Model downloads on the first run can make this take longer.'); $('transcribe').disabled=true;
  try{
    const r=await fetch('/api/transcribe',{method:'POST',body:form}); const data=await r.json();
    if(!r.ok) throw new Error(data.detail||'Transcription failed');
    events=data.events; render(); $('drumsAudio').src=data.drums_audio_url; $('rawMidi').href=data.raw_midi_url;
    $('results').hidden=false; status(`Done: ${events.length} drum events detected.`);
  }catch(e){status(e.message,true)}finally{$('transcribe').disabled=false}
};

function render(){
  $('eventRows').innerHTML='';
  events.forEach((e,i)=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${i+1}</td><td><input type="number" step="0.001" min="0" value="${e.time}"></td>
      <td><select>${Object.keys(RD8).map(d=>`<option ${d===e.drum?'selected':''}>${d}</option>`).join('')}</select></td>
      <td class="note">${e.note}</td><td><input type="number" min="1" max="127" value="${e.velocity}"></td>
      <td><button class="delete">Delete</button></td>`;
    const inputs=tr.querySelectorAll('input'), sel=tr.querySelector('select');
    inputs[0].onchange=()=>e.time=Math.max(0,Number(inputs[0].value));
    inputs[1].onchange=()=>e.velocity=Math.max(1,Math.min(127,Number(inputs[1].value)));
    sel.onchange=()=>{e.drum=sel.value;e.note=RD8[e.drum];tr.querySelector('.note').textContent=e.note};
    tr.querySelector('.delete').onclick=()=>{events.splice(i,1);render()}; $('eventRows').appendChild(tr);
  });
}

$('connectMidi').onclick=async()=>{
  if(!navigator.requestMIDIAccess) return status('Web MIDI is unavailable. Use Chrome and serve this page from localhost.',true);
  try{midiAccess=await navigator.requestMIDIAccess({sysex:false}); refreshOutputs(); midiAccess.onstatechange=refreshOutputs; status('MIDI connected. Select the RD-8 output.');}
  catch(e){status(`MIDI permission failed: ${e.message}`,true)}
};
function refreshOutputs(){
  const select=$('midiOutput'); select.innerHTML='';
  [...midiAccess.outputs.values()].forEach(o=>{const opt=document.createElement('option');opt.value=o.id;opt.textContent=o.name||o.manufacturer||o.id;select.appendChild(opt)});
  if(!select.options.length) select.innerHTML='<option>No MIDI outputs found</option>';
}
function output(){return midiAccess?.outputs.get($('midiOutput').value)}
$('play').onclick=()=>{
  stop(); const out=output(); if(!out)return status('Connect MIDI and select your RD-8 first.',true);
  const channel=Math.max(1,Math.min(16,Number($('channel').value)))-1; const start=performance.now()+100;
  events.forEach(e=>{const on=start+e.time*1000, off=on+(e.duration||.05)*1000; out.send([0x90|channel,e.note,e.velocity],on);out.send([0x80|channel,e.note,0],off)});
  playing=true; status(`Playing ${events.length} events through ${out.name}.`);
};
function stop(){timers.forEach(clearTimeout);timers=[];const out=output();if(out){for(let ch=0;ch<16;ch++)out.send([0xB0|ch,123,0])}playing=false}
$('stop').onclick=()=>{stop();status('Stopped.')};
$('quantize').onclick=async()=>{
  const r=await fetch('/api/quantize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({events,bpm:Number($('bpm').value),subdivision:16,strength:1})});
  const data=await r.json(); events=data.events;render();status('Quantized to the nearest 1/16 note.');
};
$('export').onclick=async()=>{
  const r=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({events,bpm:Number($('bpm').value),midi_channel:Number($('channel').value),filename:'rd8-drums.mid'})});
  if(!r.ok)return status('MIDI export failed.',true);const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='rd8-drums.mid';a.click();URL.revokeObjectURL(url);
};
