/* =============================================
   실버풀 (Silverful) — script.js
   - 헤더 스크롤 효과
   - 모바일 메뉴 토글
   - 부드러운 앵커 스크롤
   - 활성 네비게이션 하이라이트
   - 후기 슬라이더
   - 폼 유효성 검사 및 제출
   - 스크롤-투-탑 버튼
   - 페이드-업 애니메이션
   ============================================= */

(function () {
  'use strict';

  /* ---------- 헬퍼 ---------- */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  /* =============================================
     1. 헤더 스크롤 효과
  ============================================= */
  const header = $('#header');

  function onScroll() {
    header.classList.toggle('scrolled', window.scrollY > 20);
    scrollTopBtn.classList.toggle('visible', window.scrollY > 400);
  }

  window.addEventListener('scroll', onScroll, { passive: true });

  /* =============================================
     2. 모바일 메뉴 토글
  ============================================= */
  const hamburger = $('#hamburger');
  const mobileMenu = $('#mobileMenu');
  const overlay = $('#overlay');

  function openMenu() {
    hamburger.classList.add('open');
    mobileMenu.classList.add('open');
    overlay.classList.add('open');
    hamburger.setAttribute('aria-expanded', 'true');
    mobileMenu.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeMenu() {
    hamburger.classList.remove('open');
    mobileMenu.classList.remove('open');
    overlay.classList.remove('open');
    hamburger.setAttribute('aria-expanded', 'false');
    mobileMenu.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  hamburger.addEventListener('click', function () {
    mobileMenu.classList.contains('open') ? closeMenu() : openMenu();
  });

  overlay.addEventListener('click', closeMenu);

  // 모바일 메뉴 링크 클릭 시 닫기
  $$('.mobile-menu__link').forEach(function (link) {
    link.addEventListener('click', closeMenu);
  });

  // 창 크기 변경 시 메뉴 닫기
  window.addEventListener('resize', function () {
    if (window.innerWidth > 768) closeMenu();
  });

  /* =============================================
     3. 활성 네비게이션 하이라이트 (IntersectionObserver)
     — 데스크톱(.nav__link) + 모바일(.mobile-menu__link) 동시 처리
  ============================================= */
  const sections = $$('section[id]');
  // 두 메뉴의 링크를 하나의 배열로 합쳐서 처리
  const allNavLinks = $$('.nav__link, .mobile-menu__link');

  const sectionObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var id = entry.target.id;
          allNavLinks.forEach(function (link) {
            link.classList.toggle('active', link.getAttribute('href') === '#' + id);
          });
        }
      });
    },
    { rootMargin: '-35% 0px -55% 0px' }
  );

  sections.forEach(function (section) { sectionObserver.observe(section); });

  /* =============================================
     4. 후기 슬라이더 (섹션 존재 시에만 동작)
  ============================================= */
  // 후기 섹션이 제거된 경우 슬라이더 코드 건너뜀
  var _sliderTrack = $('#testimonialsTrack');
  if (_sliderTrack) {
    const track = _sliderTrack;
    const dots = $$('#testimonialsDots .dot');
    const cards = $$('.testimonial-card');
    let current = 0;
    let autoPlay;

    function getVisibleCount() {
      return window.innerWidth <= 768 ? 1 : 2;
    }

    function maxIndex() {
      return Math.max(0, cards.length - getVisibleCount());
    }

    function goTo(index) {
      current = Math.max(0, Math.min(index, maxIndex()));
      const cardWidth = cards[0].offsetWidth;
      const gap = 24; // 1.5rem gap
      track.style.transform = 'translateX(-' + (current * (cardWidth + gap)) + 'px)';

      dots.forEach(function (dot, i) {
        dot.classList.toggle('dot--active', i === current);
        dot.setAttribute('aria-selected', i === current ? 'true' : 'false');
      });
    }

    dots.forEach(function (dot, i) {
      dot.addEventListener('click', function () {
        clearInterval(autoPlay);
        goTo(i);
        startAutoPlay();
      });
    });

    function startAutoPlay() {
      autoPlay = setInterval(function () {
        goTo(current >= maxIndex() ? 0 : current + 1);
      }, 5000);
    }

    // 터치/스와이프 지원
    var touchStartX = 0;
    track.addEventListener('touchstart', function (e) {
      touchStartX = e.touches[0].clientX;
      clearInterval(autoPlay);
    }, { passive: true });

    track.addEventListener('touchend', function (e) {
      var diff = touchStartX - e.changedTouches[0].clientX;
      if (Math.abs(diff) > 50) {
        goTo(diff > 0 ? current + 1 : current - 1);
      }
      startAutoPlay();
    }, { passive: true });

    // 창 크기 변경 시 재계산
    window.addEventListener('resize', function () { goTo(current); });

    goTo(0);
    startAutoPlay();
  }

  /* =============================================
     5. 폼 유효성 검사 및 제출
     ─ 필드: 성함(required), 연락처(required),
             이메일(optional), 문의내용(optional)
     ─ 제출: Google Apps Script → Google Sheets 저장
  ============================================= */

  /* ── 설정 ── */
  var APPS_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbyGi-UciqCsFCaQjt78Ide-F2sZBEys5tIGF6h-kNbkC4Du-bk9JjD7CA_QfIp1qXYE/exec';
  var MAILTO_FALLBACK = 'hiexpectations90@gmail.com';

  /* ── DOM 참조 ── */
  var form = $('#contact-form');
  var submitBtn = $('#submit-btn');
  var formSuccess = $('#formSuccess');
  var resetBtn = $('#resetFormBtn');
  var formMessage = $('#form-message');

  var cfName = $('#name');
  var cfPhone = $('#phone');
  var cfEmail = $('#email');
  var cfMessage = $('#message');
  var cfAgree = $('#cf-agree');
  var msgCounter = $('#msg-counter');

  if (!form) return; // 폼이 페이지에 없으면 이후 코드 실행 안 함

  /* ── 헬퍼 ── */
  function setError(input, errId, msg) {
    input.classList.add('error');
    $('#' + errId).textContent = msg;
    input.setAttribute('aria-invalid', 'true');
  }
  function clearErr(input, errId) {
    input.classList.remove('error');
    $('#' + errId).textContent = '';
    input.removeAttribute('aria-invalid');
  }

  function isValidPhone(v) {
    return /^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(v.replace(/\s/g, ''));
  }
  function isValidEmail(v) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());
  }

  /* ── 연락처 자동 하이픈 포맷 ── */
  cfPhone.addEventListener('input', function () {
    var raw = this.value.replace(/\D/g, '').slice(0, 11);
    if (raw.length < 4) this.value = raw;
    else if (raw.startsWith('02')) {
      // 서울 02 번호: 02-xxxx-xxxx or 02-xxx-xxxx
      if (raw.length < 6) this.value = raw.slice(0, 2) + '-' + raw.slice(2);
      else if (raw.length < 10) this.value = raw.slice(0, 2) + '-' + raw.slice(2, 6) + '-' + raw.slice(6);
      else this.value = raw.slice(0, 2) + '-' + raw.slice(2, 6) + '-' + raw.slice(6, 10);
    } else {
      if (raw.length < 7) this.value = raw.slice(0, 3) + '-' + raw.slice(3);
      else this.value = raw.slice(0, 3) + '-' + raw.slice(3, 7) + '-' + raw.slice(7);
    }
    if (isValidPhone(this.value)) clearErr(this, 'err-phone');
  });

  /* ── 문자 카운터 ── */
  cfMessage.addEventListener('input', function () {
    var len = this.value.length;
    msgCounter.textContent = len + ' / 500';
    msgCounter.classList.toggle('form-counter--warn', len >= 450);
  });

  /* ── 실시간 에러 클리어 ── */
  cfName.addEventListener('input', function () {
    if (this.value.trim().length >= 2) clearErr(this, 'err-name');
  });
  cfEmail.addEventListener('input', function () {
    if (!this.value.trim() || isValidEmail(this.value)) clearErr(this, 'err-email');
  });
  cfAgree.addEventListener('change', function () {
    if (this.checked) clearErr(this, 'err-agree');
  });

  /* ── 전체 유효성 검사 ── */
  function validate() {
    var ok = true;

    // 성함: 필수, 2자 이상
    var name = cfName.value.trim();
    if (!name) {
      setError(cfName, 'err-name', '성함을 입력해 주세요.');
      ok = false;
    } else if (name.length < 2) {
      setError(cfName, 'err-name', '성함은 2자 이상 입력해 주세요.');
      ok = false;
    } else {
      clearErr(cfName, 'err-name');
    }

    // 연락처: 필수, 유효한 형식
    var phone = cfPhone.value.trim();
    if (!phone) {
      setError(cfPhone, 'err-phone', '연락처를 입력해 주세요.');
      ok = false;
    } else if (!isValidPhone(phone)) {
      setError(cfPhone, 'err-phone', '올바른 전화번호 형식으로 입력해 주세요. (예: 010-1234-5678)');
      ok = false;
    } else {
      clearErr(cfPhone, 'err-phone');
    }

    // 이메일: 선택, 입력 시 형식 검사
    var email = cfEmail.value.trim();
    if (email && !isValidEmail(email)) {
      setError(cfEmail, 'err-email', '올바른 이메일 주소를 입력해 주세요. (예: example@email.com)');
      ok = false;
    } else {
      clearErr(cfEmail, 'err-email');
    }

    // 개인정보 동의: 필수
    if (!cfAgree.checked) {
      setError(cfAgree, 'err-agree', '개인정보 처리방침에 동의해 주세요.');
      ok = false;
    } else {
      clearErr(cfAgree, 'err-agree');
    }

    return ok;
  }

  /* ── 성공 화면 표시 ── */
  function showSuccess(name) {
    form.hidden = true;
    formSuccess.hidden = false;
    var successName = $('#successName');
    if (name) successName.textContent = name + '님, 곧 연락드리겠습니다.';
    // 성공 영역으로 포커스 이동 (접근성)
    formSuccess.querySelector('.form-success__title').focus();
  }

  /* ── mailto: fallback ── */
  function sendViaMailto() {
    var name = cfName.value.trim();
    var phone = cfPhone.value.trim();
    var email = cfEmail.value.trim();
    var message = cfMessage.value.trim();

    var subject = encodeURIComponent('[실버풀 문의] ' + name + ' 님');
    var body = encodeURIComponent(
      '성함: ' + name + '\n' +
      '연락처: ' + phone + '\n' +
      (email ? '이메일: ' + email + '\n' : '') +
      (message ? '\n문의 내용:\n' + message : '')
    );
    window.location.href = 'mailto:' + MAILTO_FALLBACK +
      '?subject=' + subject + '&body=' + body;
    showSuccess(name);
  }

  /* ── Google Apps Script 제출 ── */
  function sendViaGAS(name) {
    var payload = {
      name: cfName.value.trim(),
      phone: cfPhone.value.trim(),
      email: cfEmail.value.trim(),
      message: cfMessage.value.trim(),
    };

    fetch(APPS_SCRIPT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.result === 'success') {
          form.reset();
          document.getElementById('form-message').textContent = '문의가 접수되었습니다. 빠른 시일 내에 연락드리겠습니다.';
          document.getElementById('form-message').style.color = 'green';
          showSuccess(name);
        }
      })
      .catch(function () {
        document.getElementById('form-message').textContent = '오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
        document.getElementById('form-message').style.color = 'red';
      })
      .finally(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = '문의 남기기';
      });
  }

  /* ── 폼 제출 핸들러 ── */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!validate()) {
      // 첫 번째 에러 필드로 포커스 이동
      var firstErr = form.querySelector('[aria-invalid="true"]');
      if (firstErr) firstErr.focus();
      return;
    }

    var name = cfName.value.trim();
    submitBtn.classList.add('btn--loading');
    submitBtn.disabled = true;

    sendViaGAS(name);
  });

  /* ── "다시 문의하기" 버튼 ── */
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      form.reset();
      msgCounter.textContent = '0 / 500';
      $$('.form-error').forEach(function (el) { el.textContent = ''; });
      $$('.form-input.error').forEach(function (el) { el.classList.remove('error'); });
      if (formMessage) { formMessage.textContent = ''; }
      form.hidden = false;
      formSuccess.hidden = true;
      cfName.focus();
    });
  }

  /* =============================================
     6. 스크롤-투-탑 버튼
  ============================================= */
  var scrollTopBtn = $('#scrollTop');

  scrollTopBtn.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  /* =============================================
     7. 페이드-업 애니메이션 (IntersectionObserver)
  ============================================= */
  var fadeTargets = $$('.service-card, .feature-item, .value-card, .contact__info-card, .contact__form-card');

  fadeTargets.forEach(function (el) { el.classList.add('fade-up'); });

  var fadeObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          fadeObserver.unobserve(entry.target);
        }
      });
    },
    { rootMargin: '0px 0px -60px 0px', threshold: 0.1 }
  );

  fadeTargets.forEach(function (el) { fadeObserver.observe(el); });

  /* =============================================
     8. 카드 순차 딜레이 (Stagger)
  ============================================= */
  ['.services__grid', '.features__grid'].forEach(function (gridSel) {
    var grid = $(gridSel);
    if (!grid) return;
    $$('.fade-up', grid).forEach(function (el, i) {
      el.style.transitionDelay = (i * 0.07) + 's';
    });
  });

  /* =============================================
     9. 타임라인 스크롤 애니메이션
        홀수 항목 → 왼쪽에서 슬라이드인
        짝수 항목 → 오른쪽에서 슬라이드인
  ============================================= */
  var isMobile = window.matchMedia('(max-width: 640px)');

  $$('.timeline__item').forEach(function (item, i) {
    item.classList.add('tl-hidden');
    // 0-based index: even indices are odd items (left), odd indices are even items (right)
    if (isMobile.matches) {
      // on mobile all slide from below — handled via CSS only
      item.classList.add('tl-from-left');
    } else {
      item.classList.add(i % 2 === 0 ? 'tl-from-left' : 'tl-from-right');
    }
  });

  // Update direction class when viewport crosses mobile breakpoint
  isMobile.addEventListener('change', function (e) {
    $$('.timeline__item.tl-hidden').forEach(function (item, i) {
      item.classList.remove('tl-from-left', 'tl-from-right');
      if (e.matches) {
        item.classList.add('tl-from-left');
      } else {
        item.classList.add(i % 2 === 0 ? 'tl-from-left' : 'tl-from-right');
      }
    });
  });

  var tlObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('tl-visible');
          tlObserver.unobserve(entry.target);
        }
      });
    },
    { rootMargin: '0px 0px -90px 0px', threshold: 0.12 }
  );

  $$('.timeline__item').forEach(function (item) { tlObserver.observe(item); });

})();

