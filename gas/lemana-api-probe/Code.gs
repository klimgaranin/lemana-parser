/**
 * Lemana API Probe для Google Sheets.
 *
 * Сценарии:
 * 1. Каталог по ссылке из листа Settings -> лист Catalog Results.
 * 2. Список артикулов из листа Articles -> лист Article Results.
 *
 * Все запросы и ответы пишутся в Debug Logs.
 */

const SHEETS = {
  SETTINGS: 'Settings',
  ARTICLES: 'Articles',
  CATALOG_RESULTS: 'Catalog Results',
  ARTICLE_RESULTS: 'Article Results',
  DEBUG_LOGS: 'Debug Logs',
};

const DEFAULT_SETTINGS = [
  ['catalogUrl', 'https://lemanapro.ru/catalogue/tochechnye-svetilniki/?deliveryType=%D0%A1%D0%B0%D0%BC%D0%BE%D0%B2%D0%BE%D0%B7+%D0%B2+%D0%BC%D0%B0%D0%B3%D0%B0%D0%B7%D0%B8%D0%BD%D0%B5'],
  ['apiBaseUrl', ''],
  ['apiKey', ''],
  ['requestId', ''],
  ['regionId', '34'],
  ['regionName', 'Москва, Московская область'],
  ['apiPageSize', '60'],
  ['articlesBatchSize', '30'],
  ['articlesSleepMs', '3000'],
  ['articlesMode', 'strict-then-relaxed'],
  ['maxCatalogProducts', '120'],
  ['maxArticles', '100'],
  ['cookie', ''],
  ['logResponseBodyLimit', '45000'],
];

const RESULT_HEADERS = [
  'Статус',
  'Ошибка',
  'Артикул ЛМ',
  'ССЫЛКА',
  'Наименование товара',
  'Цена на сайте',
  'Ссылка на картинку',
  'Характеристики JSON',
];

const DEBUG_HEADERS = [
  'timestamp',
  'scenario',
  'step',
  'batch',
  'method',
  'url',
  'requestPayload',
  'statusCode',
  'contentType',
  'responseHeaders',
  'responseBody',
];

let CURRENT_LOG_BODY_LIMIT = 45000;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Lemana API')
    .addItem('1. Создать/обновить листы', 'setupLemanaApiProbe')
    .addSeparator()
    .addItem('2. Запустить каталог', 'runCatalogScenario')
    .addItem('3. Запустить артикулы', 'runArticlesScenario')
    .addSeparator()
    .addItem('Очистить debug-логи', 'clearDebugLogs')
    .addToUi();
}

function setupLemanaApiProbe() {
  const ss = SpreadsheetApp.getActive();
  const settingsSheet = getOrCreateSheet_(ss, SHEETS.SETTINGS);
  const articlesSheet = getOrCreateSheet_(ss, SHEETS.ARTICLES);
  const catalogSheet = getOrCreateSheet_(ss, SHEETS.CATALOG_RESULTS);
  const articleResultsSheet = getOrCreateSheet_(ss, SHEETS.ARTICLE_RESULTS);
  const debugSheet = getOrCreateSheet_(ss, SHEETS.DEBUG_LOGS);

  if (settingsSheet.getLastRow() === 0) {
    settingsSheet.getRange(1, 1, 1, 3).setValues([['key', 'value', 'comment']]);
    const rows = DEFAULT_SETTINGS.map(([key, value]) => [key, value, settingComment_(key)]);
    settingsSheet.getRange(2, 1, rows.length, 3).setValues(rows);
  }

  if (articlesSheet.getLastRow() === 0) {
    articlesSheet.getRange(1, 1, 1, 2).setValues([['Артикул ЛМ', 'Комментарий']]);
    articlesSheet.getRange(2, 1, 3, 1).setValues([['89363286'], ['89363281'], ['89413689']]);
  }

  resetSheet_(catalogSheet, RESULT_HEADERS);
  resetSheet_(articleResultsSheet, RESULT_HEADERS);
  resetSheet_(debugSheet, DEBUG_HEADERS);

  [settingsSheet, articlesSheet, catalogSheet, articleResultsSheet, debugSheet].forEach((sheet) => {
    sheet.setFrozenRows(1);
    sheet.autoResizeColumns(1, Math.min(sheet.getMaxColumns(), 8));
  });
}

function runCatalogScenario() {
  const startedAt = Date.now();
  const ss = SpreadsheetApp.getActive();
  const settings = readSettings_(ss);
  CURRENT_LOG_BODY_LIMIT = clamp_(positiveInt_(settings.logResponseBodyLimit, 45000), 1000, 45000);
  const logs = [];

  try {
    const context = loadContext_(settings, logs, 'catalog');
    const limit = positiveInt_(settings.maxCatalogProducts, 120);
    const pageSize = clamp_(positiveInt_(settings.apiPageSize, 60), 1, 100);
    const products = [];
    const charKeys = new Set();

    for (let offset = 0; products.length < limit; offset += pageSize) {
      const searchPayload = buildSearchPayload_(context, settings, offset, pageSize);
      const searchData = postJson_(context, 'products:search', searchPayload, logs, 'catalog', 'products:search', String(offset));
      const productIds = (searchData.content || []).map(String).slice(0, limit - products.length);
      if (!productIds.length) {
        break;
      }

      const batchProducts = loadProductsBatch_(context, settings, productIds, logs, 'catalog', String(offset), false);
      batchProducts.forEach((product) => {
        Object.keys(product.characteristics || {}).forEach((key) => charKeys.add(key));
        products.push(product);
      });

      const totalCount = Number(searchData.totalCount || 0);
      if (productIds.length < pageSize || (totalCount && products.length >= totalCount)) {
        break;
      }
    }

    writeProducts_(ss, SHEETS.CATALOG_RESULTS, products);
    appendDebugLogs_(ss, logs);
    SpreadsheetApp.getUi().alert(`Каталог готов: ${products.length} товаров, характеристик: ${charKeys.size}, время: ${Math.round((Date.now() - startedAt) / 1000)} сек.`);
  } catch (error) {
    logs.push(errorLogRow_('catalog', 'fatal', '', '', '', '', '', '', String(error && error.stack || error)));
    appendDebugLogs_(ss, logs);
    throw error;
  }
}

function runArticlesScenario() {
  const startedAt = Date.now();
  const ss = SpreadsheetApp.getActive();
  const settings = readSettings_(ss);
  CURRENT_LOG_BODY_LIMIT = clamp_(positiveInt_(settings.logResponseBodyLimit, 45000), 1000, 45000);
  const logs = [];

  try {
    const context = loadContext_(settings, logs, 'articles');
    const articles = readArticles_(ss, positiveInt_(settings.maxArticles, 0));
    if (!articles.length) {
      throw new Error('Лист Articles пуст: добавь артикулы ЛМ в колонку A.');
    }

    const batchSize = clamp_(positiveInt_(settings.articlesBatchSize || settings.apiPageSize, 30), 1, 100);
    const sleepMs = Math.max(0, positiveInt_(settings.articlesSleepMs, 0));
    const products = [];
    const charKeys = new Set();

    for (let start = 0; start < articles.length; start += batchSize) {
      const productIds = articles.slice(start, start + batchSize);
      const batchProducts = loadProductsBatch_(context, settings, productIds, logs, 'articles', `${start + 1}-${start + productIds.length}`, true);
      batchProducts.forEach((product) => {
        Object.keys(product.characteristics || {}).forEach((key) => charKeys.add(key));
        products.push(product);
      });
      if (sleepMs > 0 && start + batchSize < articles.length) {
        Utilities.sleep(sleepMs);
      }
    }

    writeProducts_(ss, SHEETS.ARTICLE_RESULTS, products);
    appendDebugLogs_(ss, logs);
    SpreadsheetApp.getUi().alert(`Артикулы готовы: ${products.length} строк, характеристик: ${charKeys.size}, время: ${Math.round((Date.now() - startedAt) / 1000)} сек.`);
  } catch (error) {
    logs.push(errorLogRow_('articles', 'fatal', '', '', '', '', '', '', String(error && error.stack || error)));
    appendDebugLogs_(ss, logs);
    throw error;
  }
}

function clearDebugLogs() {
  const ss = SpreadsheetApp.getActive();
  resetSheet_(getOrCreateSheet_(ss, SHEETS.DEBUG_LOGS), DEBUG_HEADERS);
}

function loadContext_(settings, logs, scenario) {
  const catalogUrl = String(settings.catalogUrl || '').trim();
  if (!catalogUrl) {
    throw new Error('Settings.catalogUrl пуст.');
  }

  const html = fetchText_(catalogUrl, buildPageHeaders_(settings), logs, scenario, 'catalog-page', '');
  const state = extractPlpState_(html);
  const plpRoot = state.plp || {};
  const env = plpRoot.env || {};
  const productsState = ((plpRoot.plp || {}).products || {});
  const cookies = extractCookiesFromState_(plpRoot);

  const apiBaseUrl = String(settings.apiBaseUrl || env.ORCHESTRATOR_HOST || '').trim().replace(/\/?$/, '/');
  const apiKey = String(settings.apiKey || env.apiKey || env.API_KEY || '').trim();
  const familyId = String(productsState.familyId || '').trim();
  const regionId = String(settings.regionId || cookies._regionID || '34').trim();

  if (!apiBaseUrl) throw new Error('Не найден apiBaseUrl / ORCHESTRATOR_HOST.');
  if (!/^https:\/\/([^/]+\.)?lemanapro\.ru\//i.test(apiBaseUrl)) throw new Error(`Подозрительный apiBaseUrl: ${apiBaseUrl}`);
  if (!apiKey) throw new Error('Не найден apiKey. Можно указать его вручную в Settings.apiKey.');
  if (!familyId) throw new Error('Не найден familyId в catalogUrl.');

  return {
    catalogUrl,
    apiBaseUrl,
    apiKey,
    requestId: String(settings.requestId || env.requestID || env.requestId || ''),
    regionId,
    regionName: String(settings.regionName || 'Москва, Московская область'),
    familyId,
    searchMethod: String(productsState.searchMethod || 'DEFAULT'),
    facets: facetsFromUrl_(catalogUrl),
  };
}

function loadProductsBatch_(context, settings, productIds, logs, scenario, batchLabel, allowArticleMode) {
  const mode = String(settings.articlesMode || 'strict-then-relaxed').trim();
  const useRelaxedFirst = allowArticleMode && mode === 'relaxed';

  let dataItems = getProductsData_(context, productIds, logs, scenario, batchLabel, useRelaxedFirst);
  const byId = indexByProductId_(dataItems);

  if (allowArticleMode && mode === 'strict-then-relaxed') {
    const missing = productIds.filter((id) => !byId[id]);
    if (missing.length) {
      const relaxedItems = getProductsData_(context, missing, logs, scenario, `${batchLabel}:relaxed`, true);
      relaxedItems.forEach((item) => {
        if (item && item.productId) byId[String(item.productId)] = item;
      });
    }
  }

  const mediaMap = getProductsMediaSafe_(context, productIds, logs, scenario, batchLabel);
  return productIds.map((productId) => {
    const productData = byId[String(productId)];
    if (!productData) {
      return missingProduct_(productId);
    }
    return normalizeProduct_(productData, mediaMap[String(productId)]);
  });
}

function getProductsData_(context, productIds, logs, scenario, batchLabel, relaxed) {
  const payload = {
    productIds: productIds.map(String),
    filterByEligibility: !relaxed,
    deliveryDate: false,
    regionId: context.regionId,
  };
  if (!relaxed) {
    payload.facets = context.facets;
  }

  const data = postJson_(context, 'products-data:search', payload, logs, scenario, relaxed ? 'products-data:relaxed' : 'products-data:strict', batchLabel);
  return Array.isArray(data.content) ? data.content.filter((item) => item && typeof item === 'object') : [];
}

function getProductsMediaSafe_(context, productIds, logs, scenario, batchLabel) {
  try {
    const data = postJson_(
      context,
      'products-media:search',
      { productIds: productIds.map(String), requestedMedia: ['image'] },
      logs,
      scenario,
      'products-media',
      batchLabel
    );
    return data && data.data && typeof data.data === 'object' ? data.data : {};
  } catch (error) {
    logs.push(errorLogRow_(scenario, 'products-media-error', batchLabel, 'POST', '', JSON.stringify({ productIds }), '', '', String(error)));
    return {};
  }
}

function postJson_(context, method, payload, logs, scenario, step, batchLabel) {
  const url = `${context.apiBaseUrl.replace(/\/$/, '')}/${method}?lang=ru`;
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    muteHttpExceptions: true,
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    headers: buildApiHeaders_(context),
  });
  const statusCode = response.getResponseCode();
  const body = response.getContentText();
  logs.push(responseLogRow_(scenario, step, batchLabel, 'POST', url, payload, response));

  if (statusCode >= 400) {
    throw new Error(`${method}: HTTP ${statusCode}, body=${compactText_(body, 1000)}`);
  }

  try {
    return JSON.parse(body);
  } catch (error) {
    throw new Error(`${method}: ответ не JSON: ${compactText_(body, 1000)}`);
  }
}

function fetchText_(url, headers, logs, scenario, step, batchLabel) {
  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    muteHttpExceptions: true,
    headers,
  });
  logs.push(responseLogRow_(scenario, step, batchLabel, 'GET', url, '', response));
  const statusCode = response.getResponseCode();
  const body = response.getContentText();
  if (statusCode >= 400) {
    throw new Error(`GET ${url}: HTTP ${statusCode}, body=${compactText_(body, 1000)}`);
  }
  return body;
}

function buildSearchPayload_(context, settings, offset, pageSize) {
  return {
    familyIds: [context.familyId],
    limit: pageSize,
    regionId: context.regionId,
    facets: context.facets,
    suggest: true,
    filterByEligibility: true,
    showComplects: true,
    offset,
    customerId: 'undefined',
    parentFamilyId: null,
    regionName: context.regionName,
    searchMethod: context.searchMethod,
  };
}

function buildApiHeaders_(context) {
  const headers = {
    Accept: 'application/json, text/plain, */*',
    'x-api-key': context.apiKey,
    Origin: 'https://lemanapro.ru',
    Referer: 'https://lemanapro.ru/',
  };
  if (context.requestId) {
    headers['x-request-id'] = context.requestId;
  }
  return headers;
}

function buildPageHeaders_(settings) {
  const headers = {
    Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'User-Agent': 'Mozilla/5.0 GoogleAppsScript LemanaApiProbe',
  };
  const cookie = String(settings.cookie || '').trim();
  if (cookie) {
    headers.Cookie = cookie;
  }
  return headers;
}

function extractPlpState_(html) {
  const marker = 'window.INITIAL_STATE["plp"]';
  const markerPos = String(html || '').indexOf(marker);
  if (markerPos < 0) {
    throw new Error('В HTML не найден window.INITIAL_STATE["plp"].');
  }
  const start = html.indexOf('{', markerPos);
  if (start < 0) {
    throw new Error('После marker INITIAL_STATE не найден JSON.');
  }
  const jsonText = extractBalancedJson_(html, start);
  return JSON.parse(jsonText);
}

function extractBalancedJson_(text, start) {
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let pos = start; pos < text.length; pos += 1) {
    const ch = text[pos];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === '\\') {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }

    if (ch === '"') {
      inString = true;
    } else if (ch === '{') {
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        return text.slice(start, pos + 1);
      }
    }
  }
  throw new Error('INITIAL_STATE JSON не завершён.');
}

function extractCookiesFromState_(plpRoot) {
  const cookies = (plpRoot && plpRoot.cookies) || {};
  if (cookies.cookies && typeof cookies.cookies === 'object') {
    return cookies.cookies;
  }
  return typeof cookies === 'object' ? cookies : {};
}

function facetsFromUrl_(url) {
  const query = String(url || '').split('?')[1] || '';
  if (!query) return [];
  const ignored = { page: true, utm_referrer: true };
  const grouped = {};

  query.split('&').forEach((part) => {
    const pieces = part.split('=');
    const key = decodeURIComponent((pieces[0] || '').replace(/\+/g, ' '));
    const value = decodeURIComponent((pieces.slice(1).join('=') || '').replace(/\+/g, ' '));
    if (!key || ignored[key] || !value) return;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(value);
  });

  return Object.keys(grouped).map((key) => ({ id: key, values: grouped[key] }));
}

function normalizeProduct_(productData, mediaData) {
  const productId = String(productData.productId || '').trim();
  const characteristics = normalizeCharacteristics_(productData.characteristics);
  return {
    status: 'ok',
    error: '',
    article: productId,
    url: normalizeUrl_(String(productData.productLink || '')),
    name: String(productData.displayedName || '').trim(),
    price: formatPrice_(productData.price),
    image: extractImage_(productData, mediaData),
    characteristics,
  };
}

function missingProduct_(productId) {
  return {
    status: 'api_data_missing',
    error: 'API не вернул данные товара',
    article: String(productId),
    url: '',
    name: '',
    price: '',
    image: '',
    characteristics: {},
  };
}

function normalizeCharacteristics_(raw) {
  const result = {};
  if (!Array.isArray(raw)) return result;
  raw.forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const label = String(item.description || item.name || '').trim();
    const value = String(item.value || '').trim();
    if (label && value && !result[label]) {
      result[label] = value;
    }
  });
  return result;
}

function formatPrice_(price) {
  if (!price || typeof price !== 'object' || price.main_price === undefined || price.main_price === null) {
    return '';
  }
  const numberValue = Number(price.main_price);
  if (Number.isNaN(numberValue)) {
    return String(price.main_price);
  }
  return numberValue.toFixed(2).replace('.', ',');
}

function normalizeUrl_(productLink) {
  if (!productLink) return '';
  if (/^https?:\/\//i.test(productLink)) return productLink;
  return `https://lemanapro.ru${productLink.startsWith('/') ? productLink : '/' + productLink}`;
}

function extractImage_(productData, mediaData) {
  const media = mediaData && typeof mediaData === 'object' ? mediaData : {};
  if (Array.isArray(media.images)) {
    const found = media.images.find((image) => image && image.url);
    if (found) return String(found.url);
  }
  const mainPhoto = productData.mediaMainPhoto;
  if (mainPhoto && typeof mainPhoto === 'object') {
    return String(mainPhoto.desktop || mainPhoto.tablet || mainPhoto.mobile || '');
  }
  return '';
}

function indexByProductId_(items) {
  const result = {};
  (items || []).forEach((item) => {
    if (item && item.productId) {
      result[String(item.productId)] = item;
    }
  });
  return result;
}

function readSettings_(ss) {
  const sheet = getOrCreateSheet_(ss, SHEETS.SETTINGS);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    throw new Error('Лист Settings пуст. Запусти "Создать/обновить листы".');
  }
  const values = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  const settings = {};
  values.forEach(([key, value]) => {
    const cleanKey = String(key || '').trim();
    if (cleanKey) {
      settings[cleanKey] = value;
    }
  });
  return settings;
}

function readArticles_(ss, maxArticles) {
  const sheet = getOrCreateSheet_(ss, SHEETS.ARTICLES);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  const seen = {};
  const result = [];
  values.forEach(([value]) => {
    const article = String(value || '').trim();
    if (!article || seen[article]) return;
    seen[article] = true;
    if (!maxArticles || result.length < maxArticles) {
      result.push(article);
    }
  });
  return result;
}

function writeProducts_(ss, sheetName, products) {
  const sheet = getOrCreateSheet_(ss, sheetName);
  resetSheet_(sheet, RESULT_HEADERS);
  if (!products.length) return;
  const rows = products.map((product) => [
    product.status,
    product.error,
    product.article,
    product.url,
    product.name,
    product.price,
    product.image,
    JSON.stringify(product.characteristics || {}),
  ]);
  sheet.getRange(2, 1, rows.length, RESULT_HEADERS.length).setValues(rows);
  sheet.autoResizeColumns(1, RESULT_HEADERS.length);
}

function appendDebugLogs_(ss, rows) {
  if (!rows.length) return;
  const sheet = getOrCreateSheet_(ss, SHEETS.DEBUG_LOGS);
  if (sheet.getLastRow() === 0) {
    resetSheet_(sheet, DEBUG_HEADERS);
  }
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, DEBUG_HEADERS.length).setValues(rows);
}

function responseLogRow_(scenario, step, batchLabel, method, url, payload, response) {
  const headers = response.getAllHeaders ? response.getAllHeaders() : response.getHeaders();
  const contentType = String(headers['Content-Type'] || headers['content-type'] || '');
  const bodyLimit = getLogBodyLimit_();
  return [
    new Date(),
    scenario,
    step,
    batchLabel,
    method,
    url,
    typeof payload === 'string' ? payload : JSON.stringify(payload || {}),
    response.getResponseCode(),
    contentType,
    JSON.stringify(headers || {}),
    compactText_(response.getContentText(), bodyLimit),
  ];
}

function errorLogRow_(scenario, step, batchLabel, method, url, payload, statusCode, contentType, body) {
  return [
    new Date(),
    scenario,
    step,
    batchLabel,
    method,
    url,
    payload,
    statusCode,
    contentType,
    '',
    compactText_(body, getLogBodyLimit_()),
  ];
}

function getLogBodyLimit_() {
  return CURRENT_LOG_BODY_LIMIT || 45000;
}

function resetSheet_(sheet, headers) {
  sheet.clear();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.setFrozenRows(1);
}

function getOrCreateSheet_(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function positiveInt_(value, fallback) {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function clamp_(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value));
}

function compactText_(text, limit) {
  const value = String(text || '');
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}... <обрезано ${value.length - limit} символов>`;
}

function settingComment_(key) {
  const comments = {
    catalogUrl: 'Ссылка на страницу каталога LemanaPRO.',
    apiBaseUrl: 'Необязательно. Если пусто, берётся из HTML каталога.',
    apiKey: 'Необязательно. Если пусто, берётся из HTML каталога.',
    requestId: 'Необязательно. Если пусто, берётся из HTML каталога.',
    regionId: 'Обязателен для products-data:search. Москва обычно 34.',
    regionName: 'Название региона для products:search.',
    apiPageSize: 'Размер batch для каталога, 1-100.',
    articlesBatchSize: 'Размер batch для списка артикулов, 1-100.',
    articlesSleepMs: 'Пауза между batch списка артикулов, миллисекунды.',
    articlesMode: 'strict-then-relaxed или relaxed.',
    maxCatalogProducts: 'Лимит товаров для сценария каталога.',
    maxArticles: 'Лимит артикулов из листа Articles. 0 = без лимита.',
    cookie: 'Необязательно. Если HTML каталога заблокирован, можно вставить cookie.',
    logResponseBodyLimit: 'До 45000 символов, потому что у ячейки Google Sheets есть лимит.',
  };
  return comments[key] || '';
}
