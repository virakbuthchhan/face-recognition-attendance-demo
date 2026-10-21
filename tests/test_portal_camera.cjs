// Camera behavior is exercised with fake media tracks; no webcam or personal images are accessed.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const script=fs.readFileSync('backend/static/index.html','utf8').split('<script>')[1].split('</script>')[0];
function portal(getUserMedia){
 const nodes=new Map();
 function element(){return {innerHTML:'',textContent:'',value:'employee-1',hidden:false,disabled:false,open:false,srcObject:null,isConnected:true,videoWidth:1280,videoHeight:960,dataset:{},listeners:{},querySelectorAll(){return []},addEventListener(n,f){this.listeners[n]=f},append(){},showModal(){this.open=true},close(){this.open=false;this.listeners.close?.()},async play(){},getContext(){return {drawImage(){}}},toBlob(callback){callback(new Blob(['image-bytes'],{type:'image/jpeg'}))}}}
 const document={querySelector(s){if(!nodes.has(s))nodes.set(s,element());return nodes.get(s)},querySelectorAll(){return []},createElement(){return element()},addEventListener(){}};
 const context=vm.createContext({document,navigator:{mediaDevices:{getUserMedia}},window:{addEventListener(){}},URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL(){}},File,Blob,console,FormData,fetch(){throw Error('Unexpected network request')}});
 vm.runInContext(script,context);
 return {run:source=>vm.runInContext(source,context),node:s=>document.querySelector(s)};
}
function stream(){const track={stops:0,stop(){this.stops++}};return {track,getTracks:()=>[track]}}

test('camera starts only on request; closing releases its tracks',async()=>{
 const media=stream();let requests=0;
 const p=portal(async()=>{requests++;return media});
 assert.equal(requests,0);
 await p.run('openCamera()');
 assert.equal(requests,1);
 assert.equal(p.node('#capturePhoto').disabled,false);
 assert.equal(p.node('#cameraVideo').srcObject,media);
 p.run('closeCamera()');
 assert.equal(media.track.stops,1);
 assert.equal(p.node('#cameraModal').open,false);
 assert.equal(p.node('#cameraVideo').srcObject,null);
});
test('a delayed permission response after close cannot leave the camera running',async()=>{
 let resolve;const media=stream();const p=portal(()=>new Promise(r=>resolve=r));
 const pending=p.run('openCamera()');
 p.run('closeCamera()');resolve(media);await pending;
 assert.equal(media.track.stops,1);
 assert.equal(p.node('#cameraVideo').srcObject,null);
});
test('permission denial shows a recoverable upload alternative',async()=>{
 const p=portal(async()=>{const e=Error('Denied');e.name='NotAllowedError';throw e});
 await p.run('openCamera()');
 assert.equal(p.node('#cameraError').hidden,false);
 assert.match(p.node('#cameraError').textContent,/Upload photo/);
 assert.equal(p.node('#capturePhoto').disabled,true);
});
test('capture produces a preview, stops the stream, and does not upload',async()=>{
 const media=stream();const p=portal(async()=>media);
 await p.run('openCamera()');p.run("document.querySelector('#capturePhoto').onclick()");
 assert.equal(media.track.stops,1);
 assert.equal(p.run('selectedPhoto.type'),'image/jpeg');
 assert.equal(p.run('selectedPhoto.name.startsWith("camera-")'),true);
 assert.equal(p.node('#saveFace').disabled,false);
 assert.match(p.node('#photoArea').innerHTML,/Face photo preview/);
});
test('uploaded images are previewed and invalid or oversized files are rejected',()=>{
 const p=portal(async()=>stream());
 p.run("setPhoto(new Blob(['valid'],{type:'image/png'}),'face.png')");
 assert.equal(p.run('selectedPhoto.name'),'face.png');
 p.run("setPhoto(new Blob(['text'],{type:'text/plain'}),'not-a-photo.txt')");
 assert.match(p.node('#noticeText').textContent,/image file/);
 p.run("setPhoto(new Blob([new Uint8Array(8*1024*1024+1)],{type:'image/png'}),'large.png')");
 assert.match(p.node('#noticeText').textContent,/8 MB/);
 p.run('clearPhoto();paintPhoto()');
 assert.equal(p.run('selectedPhoto'),null);
 assert.equal(p.node('#saveFace').disabled,true);
});
