// Socket is global from layout.html
let audioCtx = new (window.AudioContext || window.webkitAudioContext)();
const video = document.getElementById('timer-video');

function initAudio() {
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    // Also try to play video briefly to unlock
    video.play().then(() => {
        video.pause();
        document.getElementById('click-overlay').style.display = 'none';
    }).catch(e => console.error(e));
}

function playTone(freq, duration) {
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    oscillator.type = 'triangle';
    oscillator.frequency.value = freq;
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    oscillator.start();
    gainNode.gain.setValueAtTime(0.5, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + duration);
    oscillator.stop(audioCtx.currentTime + duration);
}

socket.on('timer_update', (state) => {
    // Sync logic
    const expectedTime = 150 - state.time_left;
    if (Math.abs(video.currentTime - expectedTime) > 1.0) {
        video.currentTime = expectedTime;
    }

    if (state.running) {
        if (video.paused) video.play().catch(e => console.log(e));
    } else {
        if (!video.paused) video.pause();
    }

    // Play warning sound at 30s
    if (state.time_left === 30 && state.running) {
        playTone(600, 0.5);
    }
});

socket.on('timer_end', () => {
    playTone(440, 2.0); // Long beep
    video.pause();
    // Maybe set to end?
});

socket.on('ready_update', (data) => {
    const el = document.getElementById('ready-count');
    if (el) el.innerText = data.count;
});

function startTimer() {
    initAudio(); // Try init if not done
    playTone(880, 0.1); // High beep start
    socket.emit('start_timer');
}

function stopTimer() {
    socket.emit('stop_timer');
}

function resetTimer() {
    socket.emit('reset_timer');
    video.currentTime = 0;
}
