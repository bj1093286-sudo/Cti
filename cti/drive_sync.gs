/**
 * 통화 대시보드 ↔ 구글 드라이브 녹취 폴더 연결
 *
 * 쓰는 법 (한 번만)
 *  1. script.google.com → 새 프로젝트 → 이 코드를 통째로 붙여넣기
 *  2. 아래 FOLDER_ID 에 녹취 폴더 주소의 마지막 부분을 넣기
 *     (https://drive.google.com/drive/folders/여기부분)
 *  3. 위쪽 함수 목록에서 '설치' 선택 → 실행 → 권한 허용
 *  이후 5분마다 새 녹취를 대시보드로 보냅니다. 녹취 파일 자체는 드라이브에 그대로 있어요.
 */
const CTI_URL = '{{CTI_URL}}';
const CTI_TOKEN = '{{CTI_TOKEN}}';
const FOLDER_ID = '여기에_녹취_폴더_ID';

const AUDIO = /\.(m4a|mp4|3gp|3ga|aac|mp3|wav|amr|ogg|opus|wma)$/i;
const BATCH = 200;              // 한 번에 보내는 파일 수
const TIME_BUDGET_MS = 270000;  // 실행 시간 제한(6분) 전에 끊고 다음 회차에 이어서

function 설치() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('동기화').timeBased().everyMinutes(5).create();
  PropertiesService.getScriptProperties().deleteProperty('since');
  DriveApp.getFolderById(FOLDER_ID.trim()); // 폴더 접근 권한 확인
  동기화();
}

/** 처음부터 다시 보내기(이미 있는 녹취는 대시보드가 알아서 건너뜀) */
function 전체다시보내기() {
  PropertiesService.getScriptProperties().deleteProperty('since');
  동기화();
}

function 동기화() {
  const started = Date.now();
  const props = PropertiesService.getScriptProperties();
  const since = props.getProperty('since');
  const files = [];
  // 최상위 폴더 바로 아래 폴더 이름 = 상담원
  listChildren_(FOLDER_ID.trim(), true).forEach(function (agentDir) {
    walk_(agentDir.id, agentDir.name, since, files);
  });
  files.sort(function (a, b) { return a.created < b.created ? -1 : 1; });

  let sent = 0, newest = since, first = true;
  while (sent < files.length || first) {
    const chunk = files.slice(sent, sent + BATCH);
    chunk.forEach(function (f) { if (f.durationMs == null) f.durationMs = mp4DurationMs_(f.id, f.name); });
    post_({ files: chunk, first: first });
    first = false;
    sent += chunk.length;
    if (chunk.length) newest = chunk[chunk.length - 1].created;
    if (!chunk.length || Date.now() - started > TIME_BUDGET_MS) break;
  }
  // 다음 회차는 이번에 보낸 마지막 파일 이후부터(10분 겹치게 — 중복은 대시보드가 걸러냄)
  if (sent >= files.length) {
    props.setProperty('since', new Date(started - 10 * 60 * 1000).toISOString());
  } else if (newest) {
    props.setProperty('since', newest);
  }
  console.log('보낸 파일 ' + sent + ' / 찾은 파일 ' + files.length);
}

function walk_(folderId, agent, since, out) {
  listFiles_(folderId, since).forEach(function (f) {
    if (!AUDIO.test(f.name)) return;
    out.push({
      id: f.id, agent: agent, name: f.name, size: Number(f.size || 0), created: f.createdTime,
      durationMs: f.videoMediaMetadata && f.videoMediaMetadata.durationMillis
        ? Number(f.videoMediaMetadata.durationMillis) : null,
    });
  });
  listChildren_(folderId, true).forEach(function (sub) { walk_(sub.id, agent, since, out); });
}

function listChildren_(folderId, foldersOnly) {
  const q = "'" + folderId + "' in parents and trashed = false and mimeType " +
    (foldersOnly ? "=" : "!=") + " 'application/vnd.google-apps.folder'";
  return driveList_(q, 'files(id,name)');
}

function listFiles_(folderId, since) {
  let q = "'" + folderId + "' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'";
  if (since) q += " and createdTime > '" + since + "'";
  return driveList_(q, 'files(id,name,size,createdTime,videoMediaMetadata(durationMillis))');
}

function driveList_(q, fields) {
  const out = [];
  let pageToken = '';
  do {
    const url = 'https://www.googleapis.com/drive/v3/files?pageSize=1000&supportsAllDrives=true' +
      '&includeItemsFromAllDrives=true&corpora=allDrives&q=' + encodeURIComponent(q) +
      '&fields=' + encodeURIComponent('nextPageToken,' + fields) + (pageToken ? '&pageToken=' + pageToken : '');
    const res = UrlFetchApp.fetch(url, { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } });
    const body = JSON.parse(res.getContentText());
    (body.files || []).forEach(function (f) { out.push(f); });
    pageToken = body.nextPageToken || '';
  } while (pageToken);
  return out;
}

/** 드라이브가 길이를 안 알려 주는 m4a/mp4: 파일 앞·뒤 일부만 받아서 mvhd 상자에서 길이를 읽음 */
function mp4DurationMs_(id, name) {
  if (!/\.(m4a|mp4|3gp|3ga)$/i.test(name)) return null;
  const ranges = ['bytes=0-262143', 'bytes=-262144'];
  for (let i = 0; i < ranges.length; i++) {
    try {
      const res = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/' + id + '?alt=media&supportsAllDrives=true', {
        headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken(), Range: ranges[i] },
        muteHttpExceptions: true,
      });
      if (res.getResponseCode() >= 300) continue;
      const ms = parseMvhd_(res.getContent());
      if (ms != null) return ms;
    } catch (e) { /* 다음 방법으로 */ }
  }
  return null;
}

function parseMvhd_(b) {
  const u8 = function (i) { return b[i] & 0xff; };
  const u32 = function (i) { return ((u8(i) * 16777216) + (u8(i + 1) << 16) + (u8(i + 2) << 8) + u8(i + 3)); };
  for (let i = 0; i + 32 < b.length; i++) {
    if (u8(i) === 0x6d && u8(i + 1) === 0x76 && u8(i + 2) === 0x68 && u8(i + 3) === 0x64) { // 'mvhd'
      const v = u8(i + 4);
      const scale = v === 1 ? u32(i + 24) : u32(i + 16);
      const dur = v === 1 ? u32(i + 28) * 4294967296 + u32(i + 32) : u32(i + 20);
      return scale ? Math.round(dur * 1000 / scale) : null;
    }
  }
  return null;
}

function post_(body) {
  const res = UrlFetchApp.fetch(CTI_URL.replace(/\/$/, '') + '/api/drive/push', {
    method: 'post', contentType: 'application/json', payload: JSON.stringify(body),
    headers: { 'X-CTI-Token': CTI_TOKEN }, muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('대시보드 전송 실패 (' + res.getResponseCode() + '): ' + res.getContentText());
  }
}
