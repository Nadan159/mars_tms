// Helper to update button states
function setBtn(btn, name, value) {
    // 1. Set Hidden Input
    const input = document.querySelector(`input[name="${name}"]`);
    if (input) {
        input.value = value;
    }

    // 2. Update Visuals
    // Find parent group
    const group = btn.closest('.score-btn-group');
    if (group) {
        group.querySelectorAll('.score-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    // 3. Recalculate
    calc();
}

// Helper for generic checkbox divs
function toggleCheck(div) {
    const checkbox = div.querySelector('input[type="checkbox"]');
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        if (checkbox.checked) div.classList.add('checked');
        else div.classList.remove('checked');
        calc();
    }
}

function calc() {
    const form = document.getElementById('score-form');
    let missionPoints = 0;

    // Helper to get int val from hidden inputs or checkboxes
    const getVal = (name) => {
        const el = form.querySelector(`[name="${name}"]`);
        if (!el) return 0;
        if (el.type === 'checkbox') return el.checked ? parseInt(el.value) : 0;
        // For hidden inputs
        return parseInt(el.value) || 0;
    };

    // --- Inspection Bonus (EIB) ---
    // If Yes => 20
    let bonus = getVal('eib_bonus');

    // --- Penalty (Precision Tokens) ---
    // Formula: (6 - tokens) * (50/6)
    const tokens = getVal('precision_tokens');
    const penalty = (6 - tokens) * (50 / 6);

    // --- Missions ---

    // M01
    // Deposits (0,1,2 * 10?? No wait, let's check spec again or stick to prev 10 each)
    // Israeli Page: Deposits 0-2. Brush Yes/No.
    // Previous code: Deposits * 10
    missionPoints += getVal('m01_deposits') * 10;
    missionPoints += getVal('m01_brush');

    // M02
    missionPoints += getVal('m02_cleared') * 10;

    // M03
    missionPoints += getVal('m03_cross');
    missionPoints += getVal('m03_bonus');

    // M04
    missionPoints += getVal('m04_artifact');
    missionPoints += getVal('m04_supports');

    // M05
    missionPoints += getVal('m05_solved');

    // M06 (Count)
    missionPoints += getVal('m06_count') * 10;

    // M07
    missionPoints += getVal('m07_millstone');

    // M08 (Count)
    missionPoints += getVal('m08_count') * 10;

    // M09
    missionPoints += getVal('m09_roof');
    missionPoints += getVal('m09_wares');

    // M10
    missionPoints += getVal('m10_tipped');
    missionPoints += getVal('m10_removed');

    // M11
    missionPoints += getVal('m11_raised');
    missionPoints += getVal('m11_flag');

    // M12 
    missionPoints += getVal('m12_sand');
    missionPoints += getVal('m12_ship');

    // M13
    missionPoints += getVal('m13_upright');

    // M14 (Checkboxes)
    // Each checked item is 5 points (based on specs)
    missionPoints += getVal('m14_brush');
    missionPoints += getVal('m14_opp_cart');
    missionPoints += getVal('m14_pan');
    missionPoints += getVal('m14_topsoil');
    missionPoints += getVal('m14_ore');
    missionPoints += getVal('m14_artifact');
    missionPoints += getVal('m14_millstone');

    // M15 (Count)
    missionPoints += getVal('m15_count') * 10;

    // --- Final Calculation ---
    // final_score = max(total_mission + bonus - penalty, 0)
    let total = missionPoints + bonus - penalty;
    if (total < 0) total = 0;

    // Update UI
    const totalEl = document.getElementById('total-score');
    if (totalEl) totalEl.innerText = Math.round(total);
}

// Initial calc
document.addEventListener('DOMContentLoaded', () => {
    // If checkboxes are pre-checked by browser (reload), sync visuals
    document.querySelectorAll('.score-checkbox-item').forEach(div => {
        const chk = div.querySelector('input');
        if (chk && chk.checked) div.classList.add('checked');
    });

    // Also sync buttons if needed (usually simple reset)
    calc();

    // Re-bind signature pads
    initSigs();
});

// Image modal
function showMissionImage(missionId) {
    const modal = document.getElementById('image-modal');
    const img = document.getElementById('modal-img');
    const cleanId = missionId.replace(/^M0/, 'M');
    img.src = `/static/mission_images/${cleanId}.png`;
    modal.style.display = 'flex';
}

function closeModal(event, force) {
    if (force || event.target.id === 'image-modal') {
        document.getElementById('image-modal').style.display = 'none';
        document.getElementById('modal-img').src = '';
    }
}

// Signatures
let sigRef, sigTeam;
function initSigs() {
    const canvasRef = document.getElementById('sig-ref');
    const canvasTeam = document.getElementById('sig-team');

    function resizeCanvas(canvas) {
        if (!canvas) return;
        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        canvas.width = canvas.offsetWidth * ratio;
        canvas.height = canvas.offsetHeight * ratio;
        canvas.getContext("2d").scale(ratio, ratio);
    }

    if (canvasRef && canvasTeam) {
        resizeCanvas(canvasRef);
        resizeCanvas(canvasTeam);
        // Only init if not already (simple check or re-init OK)
        if (typeof SignaturePad !== 'undefined') {
            sigRef = new SignaturePad(canvasRef);
            sigTeam = new SignaturePad(canvasTeam);
            window.addEventListener("resize", function () {
                resizeCanvas(canvasRef);
                resizeCanvas(canvasTeam);
                sigRef.clear();
                sigTeam.clear();
            });
        }
    }
}

function clearSig(type) {
    if (type === 'ref' && sigRef) sigRef.clear();
    else if (sigTeam) sigTeam.clear();
}

function submitScore() {
    const teamId = document.getElementById('team-select').value;
    const refName = document.getElementById('ref-name').value;
    const total = parseInt(document.getElementById('total-score').innerText);

    if (!teamId || teamId === 'No teams found') {
        alert('Please select a team');
        return;
    }

    if (!refName.trim()) {
        alert('Referee Name is required');
        return;
    }

    if (sigRef.isEmpty() || sigTeam.isEmpty()) {
        alert('Both Referee and Team Member signatures are required!');
        return;
    }

    // Collect all data
    const formData = new FormData(document.getElementById('score-form'));
    const details = {};
    formData.forEach((value, key) => details[key] = value);

    // Add meta
    details['referee_name'] = refName;
    details['sig_ref'] = sigRef.toDataURL();
    details['sig_team'] = sigTeam.toDataURL();

    fetch('/api/scores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            team_id: teamId,
            total: total,
            details: JSON.stringify(details)
        })
    })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
            } else {
                alert('Score Submitted Successfully!');
                location.href = '/scoreboard';
            }
        });
}
