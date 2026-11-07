// Telegram Web App bilan umumiy bog'lanish
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  const inTelegram = !!(tg && tg.initData);

  function cookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }
  window.csrfToken = () => cookie('csrftoken');

  // Tasdiqlash oynasi: Telegramda o'zining, brauzerda oddiy confirm
  window.askConfirm = function (text, done) {
    if (inTelegram && tg.isVersionAtLeast('6.2')) tg.showConfirm(text, ok => ok && done());
    else if (window.confirm(text)) done();
  };

  document.addEventListener('submit', event => {
    const form = event.target;
    if (form.dataset.confirm && !form.dataset.confirmed) {
      event.preventDefault();
      askConfirm(form.dataset.confirm, () => {
        form.dataset.confirmed = '1';
        form.requestSubmit ? form.requestSubmit() : form.submit();
      });
    }
  });

  if (inTelegram) {
    tg.ready();
    tg.expand();
    // Shu qurilmada boshqa Telegram hisobi ochilgan bo'lsa, sessiyani yangilaymiz
    const current = document.body.dataset.tgId;
    const actual = tg.initDataUnsafe && tg.initDataUnsafe.user && String(tg.initDataUnsafe.user.id);
    if (current !== undefined && current !== '' && actual && current !== actual) {
      fetch('/auth/telegram/', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ init_data: tg.initData }),
      }).then(r => r.ok && location.replace('/'));
    }
  }
})();
