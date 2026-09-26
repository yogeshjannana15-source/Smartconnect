function togglePassword(id, button){
  const input=document.getElementById(id);
  if(!input)return;
  input.type=input.type==="password"?"text":"password";
  button.textContent=input.type==="password"?"Show":"Hide";
}
function setupRegistrationChecks(){
  const email=document.getElementById("email"), phone=document.getElementById("phone");
  const emailStatus=document.getElementById("emailStatus"), phoneStatus=document.getElementById("phoneStatus");
  async function check(url,status){
    const value=url.includes("email")?email.value.trim():phone.value.trim();
    if(!value){status.textContent="";return;}
    try{
      const r=await fetch(url+encodeURIComponent(value)); const data=await r.json();
      status.textContent=data.available?"✓ Available":"✕ Already used";
      status.className="field-status "+(data.available?"ok":"bad");
    }catch(e){status.textContent="";}
  }
  email.addEventListener("blur",()=>check("/api/check-email?email=",emailStatus));
  phone.addEventListener("blur",()=>check("/api/check-phone?phone=",phoneStatus));
  phone.addEventListener("input",()=>{phone.value=phone.value.replace(/\D/g,"").slice(0,10)});
  const form=document.getElementById("registerForm");
  form.addEventListener("submit",(e)=>{
    const p=document.getElementById("password").value, c=document.getElementById("confirm_password").value;
    if(p!==c){e.preventDefault();alert("Passwords do not match. Please enter the same password.");}
    if(phone.value.length!==10){e.preventDefault();alert("Phone number must contain exactly 10 digits.");}
  });
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll(".flash").forEach(el=>setTimeout(()=>{if(el.parentElement)el.remove()},7000));
});
