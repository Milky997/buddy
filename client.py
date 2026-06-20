import requests, pyaudio, wave, threading, pygame, time, queue, os
SRV = os.getenv("BUDDY_SERVER", "http://localhost:8000")
SID = "user1"
P = {"1": ("cheerful","Buddy (cheerful)"),"2": ("calm","Buddy (calm)"),"3": ("coach","Coach")}
def sel():
    print("\\nSelect persona:")
    for k,(_,n) in P.items(): print(f"  [{k}] {n}")
    c = input("Enter (Enter=cheerful): ").strip()
    return P.get(c, ("cheerful","B"))[0]
def sp(pk):
    r = requests.post(f"{SRV}/set_persona", params={"session_id": SID, "persona_key": pk})
    print(f"  -> {r.json().get('display_name', pk)}")
def rec(fn="in.wav"):
    pa = pyaudio.PyAudio()
    st = pa.open(format=pyaudio.paInt16,channels=1,rate=16000,input=True,frames_per_buffer=1024)
    f,rc = [],True
    def rt():
        while rc: f.append(st.read(1024,exception_on_overflow=False))
    t = threading.Thread(target=rt,daemon=True); t.start()
    print("Recording... Enter=stop"); input(); rc=False; t.join()
    st.stop_stream();st.close();pa.terminate()
    wf = wave.open(fn,"wb"); wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(16000)
    wf.writeframes(b"".join(f)); wf.close()
def ply(r):
    q = queue.Queue()
    def rcv():
        b = b""
        for c in r.iter_content(chunk_size=None):
            b += c
            while len(b)>=4:
                n = int.from_bytes(b[:4],"big")
                if len(b)<4+n: break
                q.put(b[4:4+n]); b = b[4+n:]
        q.put(None)
    def plyr():
        pygame.mixer.init(); i = 0
        while True:
            d = q.get()
            if d is None: break
            fn = f"t{i}.wav"; i+=1
            with open(fn,"wb") as f: f.write(d)
            pygame.mixer.music.load(fn)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
        pygame.mixer.quit()
    t1=threading.Thread(target=rcv,daemon=True);t2=threading.Thread(target=plyr,daemon=True)
    t1.start();t2.start();t1.join();t2.join()
print("English Buddy Client"); pk=sel(); sp(pk)
while True:
    try:
        c = input("\\nEnter=record, /switch=persona: ").strip()
        if c=="/switch": pk=sel();sp(pk);continue
        rec()
        with open("in.wav","rb") as f:
            r = requests.post(f"{SRV}/chat",files={"audio":("in.wav",f,"audio/wav")},params={"session_id":SID},stream=True,timeout=120)
        ply(r)
    except KeyboardInterrupt: print("Bye"); break
