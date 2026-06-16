const bridge = window.AstrBotPluginPage;
let allWeatherTypes = [];
let fishNameSet = null;
let lureNameSet = null;

// --- Custom Dialog (sandbox-safe) ---
function showDialog(msg, onOk, onCancel) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:2000;display:flex;align-items:center;justify-content:center';
  const box = document.createElement('div');
  box.style.cssText = 'background:var(--card-bg,#fff);color:var(--text,#1a1a1a);padding:24px;border-radius:8px;min-width:300px;box-shadow:0 4px 20px rgba(0,0,0,0.3)';
  box.innerHTML = `<p style="margin-bottom:16px">${esc(msg)}</p>
    <div style="display:flex;gap:8px;justify-content:flex-end">
    <button id="dlg-cancel" class="btn btn-outline">取消</button>
    <button id="dlg-ok" class="btn btn-danger">确认</button></div>`;
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  overlay.querySelector('#dlg-ok').addEventListener('click', () => { overlay.remove(); if(onOk)onOk(); });
  overlay.querySelector('#dlg-cancel').addEventListener('click', () => { overlay.remove(); if(onCancel)onCancel(); });
}

// --- Toast ---
function toast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast toast-' + (type || 'success');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
}

// =================== Tab Switching ===================
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'fish') loadFish();
    else if (t.dataset.tab === 'lure') loadLures();
    else if (t.dataset.tab === 'weather') loadWeather();
    else if (t.dataset.tab === 'shop') loadShop();
  });
});

// =================== Fish ===================
function showFishModal(fish) {
  const modal = document.getElementById('fish-modal');
  document.getElementById('fish-id').value = fish ? fish.name : '';
  document.getElementById('fish-name').value = fish ? fish.name : '';
  document.getElementById('fish-type').value = fish ? fish.fish_type : '普通鱼';
  document.getElementById('fish-region').value = fish ? fish.region || '' : '';
  document.getElementById('fish-ground').value = fish ? fish.fishing_ground || '' : '';
  document.getElementById('fish-bait').value = fish ? fish.bait || '' : '';
  document.getElementById('fish-weather').value = fish ? fish.weather || '' : '';
  document.getElementById('fish-min-size').value = fish ? fish.min_size : 3.9;
  document.getElementById('fish-min-big-size').value = fish ? fish.min_big_size : 9.2;
  document.getElementById('fish-max-size').value = fish ? fish.max_size : 9.7;
  document.getElementById('fish-base-value').value = fish ? fish.base_value : 50;
  document.getElementById('fish-name').readOnly = !!fish;
  document.getElementById('fish-modal-title').textContent = fish ? '编辑鱼类' : '新增鱼类';
  modal.classList.add('show');
}

function hideFishModal() {
  document.getElementById('fish-modal').classList.remove('show');
}

document.getElementById('btn-add-fish').addEventListener('click', () => showFishModal(null));
document.getElementById('btn-fish-cancel').addEventListener('click', hideFishModal);
document.getElementById('btn-fish-save').addEventListener('click', saveFish);

async function saveFish() {
  const isUpdate = !!document.getElementById('fish-id').value;
  const name = document.getElementById('fish-name').value.trim();
  const data = {
    name: name,
    fish_type: document.getElementById('fish-type').value,
    region: document.getElementById('fish-region').value.trim(),
    fishing_ground: document.getElementById('fish-ground').value.trim(),
    bait: document.getElementById('fish-bait').value.trim(),
    weather: document.getElementById('fish-weather').value.trim(),
    min_size: parseFloat(document.getElementById('fish-min-size').value) || 0,
    min_big_size: parseFloat(document.getElementById('fish-min-big-size').value) || 0,
    max_size: parseFloat(document.getElementById('fish-max-size').value) || 0,
    base_value: parseInt(document.getElementById('fish-base-value').value) || 0,
  };
  if (!data.name) { toast('请输入鱼名', 'error'); return; }

  if (!isUpdate && fishNameSet && fishNameSet.has(name)) {
    showDialog('鱼类「' + esc(name) + '」已存在，是否修改已有数据？', async () => {
      try {
        const result = await bridge.apiPost('admin/fish/update', data);
        toast(result.message || '更新成功');
        hideFishModal();
        loadFish();
      } catch (e) {
        toast('保存失败: ' + (e.message || '未知错误'), 'error');
      }
    });
    return;
  }

  try {
    const endpoint = isUpdate ? 'admin/fish/update' : 'admin/fish/add';
    const result = await bridge.apiPost(endpoint, data);
    toast(result.message || '保存成功');
    hideFishModal();
    loadFish();
  } catch (e) {
    toast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
}

async function deleteFish(name) {
  showDialog('确定删除 ' + esc(name) + ' 吗？', async () => {
    try {
      const result = await bridge.apiPost('admin/fish/delete', { name });
      toast(result.message || '删除成功');
      loadFish();
    } catch (e) {
      toast('删除失败: ' + (e.message || '未知错误'), 'error');
    }
  });
}

async function loadFish() {
  try {
    const data = await bridge.apiGet('admin/fish/list');
    const tbody = document.getElementById('fish-tbody');
    fishNameSet = new Set((data.fish || []).map(f => f.name));

    // Sort by region, fishing_ground, fish_type priority, name
    const typeOrder = { '鱼皇': 0, '鱼王': 1, '普通鱼': 2 };
    const sorted = [...(data.fish || [])].sort((a, b) => {
      const r = (a.region || '').localeCompare(b.region || '');
      if (r !== 0) return r;
      const g = (a.fishing_ground || '').localeCompare(b.fishing_ground || '');
      if (g !== 0) return g;
      const ta = typeOrder[a.fish_type] ?? 3;
      const tb = typeOrder[b.fish_type] ?? 3;
      if (ta !== tb) return ta - tb;
      return (a.name || '').localeCompare(b.name || '');
    });

    if (sorted.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = sorted.map(f => {
      let tb = 'badge-normal';
      if (f.fish_type === '鱼王') tb = 'badge-king';
      else if (f.fish_type === '鱼皇') tb = 'badge-emperor';
      const fStr = JSON.stringify(f).replace(/"/g, '"').replace(/'/g, '&#39;');
      return `<tr>
        <td>${esc(f.name)}</td>
        <td><span class="badge ${tb}">${esc(f.fish_type)}</span></td>
        <td>${esc(f.region||'-')}</td>
        <td>${esc(f.fishing_ground||'-')}</td>
        <td>${esc(f.bait||'通杀')}</td>
        <td>${esc(f.weather||'不限')}</td>
        <td>${f.min_size}-${f.max_size}cm</td>
        <td>${f.base_value}G</td>
        <td>
          <button class="btn btn-outline btn-sm edit-fish-btn" data-fish='${fStr}'>✏️</button>
          <button class="btn btn-danger btn-sm delete-fish-btn" data-name="${esc(f.name)}">🗑️</button>
        </td>
      </tr>`;
    }).join('');
    document.querySelectorAll('.edit-fish-btn').forEach(btn => {
      btn.addEventListener('click', () => showFishModal(JSON.parse(btn.getAttribute('data-fish'))));
    });
    document.querySelectorAll('.delete-fish-btn').forEach(btn => {
      btn.addEventListener('click', () => deleteFish(btn.getAttribute('data-name')));
    });
  } catch (e) {
    document.getElementById('fish-tbody').innerHTML = '<tr><td colspan="9" class="empty">加载失败: ' + esc(e.message || '') + '</td></tr>';
  }
}

// =================== Lure ===================
function showLureModal(lure) {
  const modal = document.getElementById('lure-modal');
  document.getElementById('lure-id').value = lure ? lure.name : '';
  document.getElementById('lure-name').value = lure ? lure.name : '';
  document.getElementById('lure-price').value = lure ? lure.price : 200;
  document.getElementById('lure-sellable').value = lure ? (lure.sellable ? '1' : '0') : '1';
  document.getElementById('lure-name').readOnly = !!lure;
  document.getElementById('lure-modal-title').textContent = lure ? '编辑鱼饵' : '新增鱼饵';
  modal.classList.add('show');
}

function hideLureModal() {
  document.getElementById('lure-modal').classList.remove('show');
}

document.getElementById('btn-add-lure').addEventListener('click', () => showLureModal(null));
document.getElementById('btn-lure-cancel').addEventListener('click', hideLureModal);
document.getElementById('btn-lure-save').addEventListener('click', saveLure);

async function saveLure() {
  const isUpdate = !!document.getElementById('lure-id').value;
  const name = document.getElementById('lure-name').value.trim();
  const data = {
    name: name,
    price: parseInt(document.getElementById('lure-price').value) || 0,
    sellable: document.getElementById('lure-sellable').value === '1',
  };
  if (!data.name) { toast('请输入鱼饵名', 'error'); return; }

  if (!isUpdate && lureNameSet && lureNameSet.has(name)) {
    showDialog('鱼饵「' + esc(name) + '」已存在，是否修改已有数据？', async () => {
      try {
        const result = await bridge.apiPost('admin/lure/update', data);
        toast(result.message || '更新成功');
        hideLureModal();
        loadLures();
      } catch (e) {
        toast('保存失败: ' + (e.message || '未知错误'), 'error');
      }
    });
    return;
  }

  try {
    const endpoint = isUpdate ? 'admin/lure/update' : 'admin/lure/add';
    const result = await bridge.apiPost(endpoint, data);
    toast(result.message || '保存成功');
    hideLureModal();
    loadLures();
  } catch (e) {
    toast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
}

async function deleteLure(name) {
  showDialog('确定删除 ' + esc(name) + ' 吗？', async () => {
    try {
      const result = await bridge.apiPost('admin/lure/delete', { name });
      toast(result.message || '删除成功');
      loadLures();
    } catch (e) {
      toast('删除失败: ' + (e.message || '未知错误'), 'error');
    }
  });
}

async function loadLures() {
  try {
    const data = await bridge.apiGet('admin/lure/list');
    const tbody = document.getElementById('lure-tbody');
    lureNameSet = new Set((data.lures || []).map(l => l.name));

    // Sort by name
    const sorted = [...(data.lures || [])].sort((a, b) => (a.name || '').localeCompare(b.name || ''));

    if (sorted.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = sorted.map(l => {
      const lStr = JSON.stringify(l).replace(/"/g, '"').replace(/'/g, '&#39;');
      return `<tr>
      <td>${esc(l.name)}</td>
      <td>${l.price}G</td>
      <td><span class="badge ${l.sellable ? 'badge-yes' : 'badge-no'}">${l.sellable ? '是' : '否'}</span></td>
      <td>
        <button class="btn btn-outline btn-sm edit-lure-btn" data-lure='${lStr}'>✏️</button>
        <button class="btn btn-danger btn-sm delete-lure-btn" data-name="${esc(l.name)}">🗑️</button>
      </td>
    </tr>`;
    }).join('');
    document.querySelectorAll('.edit-lure-btn').forEach(btn => {
      btn.addEventListener('click', () => showLureModal(JSON.parse(btn.getAttribute('data-lure'))));
    });
    document.querySelectorAll('.delete-lure-btn').forEach(btn => {
      btn.addEventListener('click', () => deleteLure(btn.getAttribute('data-name')));
    });
  } catch (e) {
    document.getElementById('lure-tbody').innerHTML = '<tr><td colspan="4" class="empty">加载失败: ' + esc(e.message || '') + '</td></tr>';
  }
}

// =================== Weather ===================
async function loadWeather() {
  try {
    const data = await bridge.apiGet('admin/weather/list');
    allWeatherTypes = data.weather_types || [];
    document.getElementById('weather-types-input').value = allWeatherTypes.join(',');
    const select = document.getElementById('set-weather-type');
    select.innerHTML = allWeatherTypes.map(w => `<option value="${esc(w)}">${esc(w)}</option>`).join('');
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('set-weather-date').value = today;
    const grid = document.getElementById('weather-grid');
    if (!data.current || data.current.length === 0) {
      grid.innerHTML = '<div class="empty">暂无天气数据</div>';
      return;
    }
    grid.innerHTML = data.current.map(w => `<div class="weather-card"><div class="date">${w.date} ${w.label}</div><div>${w.weather}</div></div>`).join('');
  } catch (e) {
    document.getElementById('weather-grid').innerHTML = '<div class="empty">加载失败: ' + esc(e.message || '') + '</div>';
  }
}

document.getElementById('btn-refresh-weather').addEventListener('click', loadWeather);
document.getElementById('btn-save-weather-types').addEventListener('click', async () => {
  const types = document.getElementById('weather-types-input').value.split(',').map(s => s.trim()).filter(Boolean);
  try {
    const result = await bridge.apiPost('admin/weather/save-types', { weather_types: types });
    toast(result.message || '保存成功');
    loadWeather();
  } catch (e) {
    toast('保存失败: ' + (e.message || '未知错误'), 'error');
  }
});
document.getElementById('btn-set-weather').addEventListener('click', async () => {
  const wdate = document.getElementById('set-weather-date').value;
  const slot = parseInt(document.getElementById('set-weather-slot').value);
  const weather = document.getElementById('set-weather-type').value;
  try {
    const result = await bridge.apiPost('admin/weather/set', { date: wdate, slot, weather });
    toast(result.message || '设置成功');
    loadWeather();
  } catch (e) {
    toast('设置失败: ' + (e.message || '未知错误'), 'error');
  }
});

// =================== Shop ===================
async function loadShop() {
  try {
    const data = await bridge.apiGet('admin/shop/list');
    const tbody = document.getElementById('shop-tbody');
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty">暂无商品</td></tr>';
      return;
    }
    tbody.innerHTML = data.items.map(item => `<tr><td>${item.id}</td><td>${esc(item.name)}</td><td>${item.price}G</td></tr>`).join('');
  } catch (e) {
    document.getElementById('shop-tbody').innerHTML = '<tr><td colspan="3" class="empty">加载失败: ' + esc(e.message || '') + '</td></tr>';
  }
}

// =================== Init ===================
async function init() {
  await bridge.ready();
  bridge.onContext(() => {});
  loadFish();
}
init();