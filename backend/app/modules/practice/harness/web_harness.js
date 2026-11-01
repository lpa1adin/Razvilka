/*
  Проверка веб-заданий. ОДИН файл для двух мест:
  - в браузере — внутри изолированного iframe (страница /sandbox.html);
  - в runner — в Chromium через Playwright.
  Встраивается в страницу ученика ДО его скрипта. Перед ним задаются window.__rzMode ('preview' | 'check')
  и window.__rzWidth (375 | 768 | 1280).

  API для тестов задания:
    test('Название проверки', () => { expect(условие, 'что не так') })
    test('На телефоне — в колонку', { width: 375 }, async () => { ... })
    $(sel), $$(sel), style(el, 'свойство'), click(el), wait(ms)
*/
;(function () {
  var tests = []
  var errors = []
  var report = function (message) {
    try {
      if (window.parent !== window) window.parent.postMessage(Object.assign({ rz: true }, message), '*')
    } catch (e) {}
  }

  // Консоль и ошибки страницы — в панель «Результат»
  ;['log', 'info', 'warn', 'error'].forEach(function (level) {
    var original = console[level]
    console[level] = function () {
      var text = Array.prototype.map
        .call(arguments, function (a) {
          try {
            return typeof a === 'string' ? a : JSON.stringify(a)
          } catch (e) {
            return String(a)
          }
        })
        .join(' ')
      report({ type: 'console', level: level, text: text })
      return original.apply(console, arguments)
    }
  })
  window.addEventListener('error', function (event) {
    var text = event.message + (event.lineno ? ' (строка ' + event.lineno + ')' : '')
    errors.push(text)
    report({ type: 'console', level: 'error', text: text })
  })

  window.test = function (name, options, fn) {
    if (typeof options === 'function') {
      fn = options
      options = {}
    }
    tests.push({ name: name, width: options.width || 1280, fn: fn })
  }
  window.expect = function (condition, message) {
    if (!condition) {
      var failure = new Error(message || 'Проверка не прошла')
      failure.name = 'RzCheck'
      throw failure
    }
  }
  window.$ = function (selector) {
    return document.querySelector(selector)
  }
  window.$$ = function (selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector))
  }
  window.style = function (el, prop) {
    return el ? getComputedStyle(el).getPropertyValue(prop).trim() : ''
  }
  window.wait = function (ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms)
    })
  }
  window.click = function (el) {
    if (!el) throw new Error('Нечего нажимать: элемент не найден')
    el.click()
    return window.wait(50)
  }

  async function runTests() {
    var width = window.__rzWidth || 1280
    var results = []
    var mine = tests.filter(function (t) {
      return t.width === width
    })
    for (var i = 0; i < mine.length; i++) {
      var t = mine[i]
      try {
        await Promise.race([
          Promise.resolve().then(t.fn),
          new Promise(function (_, reject) {
            setTimeout(function () {
              reject(new Error('Проверка не дождалась результата за 3 секунды'))
            }, 3000)
          }),
        ])
        results.push({ name: t.name, width: width, passed: true, message: '' })
      } catch (e) {
        // Не-expect ошибка — обычно нужного элемента нет на странице, и проверка не смогла его измерить
        var text = (e && e.message) || String(e)
        results.push({ name: t.name, width: width, passed: false, message: e && e.name === 'RzCheck' ? text : 'Не удалось проверить: ' + text })
      }
    }
    var payload = { type: 'results', width: width, results: results, errors: errors }
    window.__rzResults = payload
    report(payload)
  }

  if (window.__rzMode === 'check') {
    window.addEventListener('load', function () {
      setTimeout(runTests, 30)
    })
  }
})()
