"""
Token Manager Module
====================
إدارة Access Tokens و Refresh Tokens
"""

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import base64

from rich.console import Console

console = Console()


@dataclass
class TokenData:
    """بيانات الـ Token"""
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int
    token_type: str = "Bearer"
    scope: str = "openid profile email offline_access"
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
    
    @property
    def is_expired(self) -> bool:
        """التحقق من انتهاء صلاحية الـ token"""
        if self.created_at is None:
            return True
        elapsed = time.time() - self.created_at
        # نعتبره منتهي قبل 5 دقائق من الانتهاء الفعلي
        return elapsed >= (self.expires_in - 300)
    
    @property
    def time_remaining(self) -> int:
        """الوقت المتبقي بالثواني"""
        if self.created_at is None:
            return 0
        elapsed = time.time() - self.created_at
        remaining = self.expires_in - elapsed
        return max(0, int(remaining))
    
    def to_dict(self) -> dict:
        """تحويل إلى قاموس"""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "expires_in": self.expires_in,
            "token_type": self.token_type,
            "scope": self.scope,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TokenData":
        """إنشاء من قاموس"""
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            id_token=data.get("id_token", ""),
            expires_in=data.get("expires_in", 86400),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", "openid profile email offline_access"),
            created_at=data.get("created_at")
        )


class TokenManager:
    """
    إدارة الـ Tokens
    
    - تحميل وحفظ tokens
    - التحقق من الصلاحية
    - تجديد الـ token
    """
    
    def __init__(self, tokens_file: Path):
        """
        تهيئة مدير الـ Tokens
        
        Args:
            tokens_file: مسار ملف الـ tokens
        """
        self.tokens_file = Path(tokens_file)
        self._token_data: Optional[TokenData] = None
    
    def load(self) -> bool:
        """
        تحميل الـ tokens من الملف
        
        Returns:
            True إذا تم التحميل بنجاح
        """
        if not self.tokens_file.exists():
            console.print("[yellow]⚠ ملف الـ tokens غير موجود[/yellow]")
            return False
        
        try:
            with open(self.tokens_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            
            self._token_data = TokenData.from_dict(data)
            
            if self._token_data.is_expired:
                console.print("[yellow]⚠ الـ Token منتهي الصلاحية[/yellow]")
                return False
            
            hours = self._token_data.time_remaining // 3600
            minutes = (self._token_data.time_remaining % 3600) // 60
            console.print(f"[green]✓ تم تحميل Token (صالح لـ {hours}h {minutes}m)[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]✗ خطأ في تحميل الـ tokens: {e}[/red]")
            return False
    
    def save(self) -> bool:
        """
        حفظ الـ tokens إلى الملف
        
        Returns:
            True إذا تم الحفظ بنجاح
        """
        if self._token_data is None:
            return False
        
        try:
            self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump(self._token_data.to_dict(), f, indent=2)
            
            console.print("[green]✓ تم حفظ الـ tokens[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]✗ خطأ في حفظ الـ tokens: {e}[/red]")
            return False
    
    def set_tokens(self, data: dict) -> None:
        """
        تعيين tokens جديدة
        
        Args:
            data: بيانات الـ tokens
        """
        self._token_data = TokenData.from_dict(data)
        self._token_data.created_at = time.time()
        self.save()
    
    @property
    def access_token(self) -> Optional[str]:
        """الحصول على access_token"""
        if self._token_data and not self._token_data.is_expired:
            return self._token_data.access_token
        return None
    
    @property
    def refresh_token(self) -> Optional[str]:
        """الحصول على refresh_token"""
        if self._token_data:
            return self._token_data.refresh_token
        return None
    
    @property
    def is_valid(self) -> bool:
        """التحقق من صلاحية الـ token"""
        return self._token_data is not None and not self._token_data.is_expired
    
    def get_auth_header(self) -> dict:
        """
        الحصول على header المصادقة
        
        Returns:
            قاموس headers
        """
        if self.access_token:
            return {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
        return {}
    
    def decode_token_info(self) -> Optional[dict]:
        """
        فك تشفير معلومات الـ token (JWT)
        
        Returns:
            معلومات الـ token
        """
        if not self.access_token:
            return None
        
        try:
            # JWT format: header.payload.signature
            parts = self.access_token.split(".")
            if len(parts) != 3:
                return None
            
            # فك تشفير الـ payload
            payload = parts[1]
            # إضافة padding إذا لزم الأمر
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
            
        except Exception:
            return None

