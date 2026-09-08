#include "Core/PTKGuardBase.h"

#include "Components/CapsuleComponent.h"
#include "Components/PTKHealthComponent.h"
#include "Analytics/PTKAnalyticsSubsystem.h"
#include "Core/PTKBattlefield.h"
#include "PaperSprite.h"
#include "PaperSpriteComponent.h"
#include "ProtectTheKing2D.h"

APTKGuardBase::APTKGuardBase()
{
	PrimaryActorTick.bCanEverTick = false;

	Capsule = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Capsule"));
	SetRootComponent(Capsule);
	Capsule->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Capsule->SetCollisionObjectType(ECC_WorldDynamic);
	Capsule->SetCollisionResponseToAllChannels(ECR_Overlap);
	Capsule->SetGenerateOverlapEvents(true);

	HealthComponent = CreateDefaultSubobject<UPTKHealthComponent>(TEXT("Health"));

	RuinsSprite = CreateDefaultSubobject<UPaperSpriteComponent>(TEXT("Ruins"));
	RuinsSprite->SetupAttachment(Capsule);
	RuinsSprite->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RuinsSprite->SetVisibility(false);
	// Behind the characters, in front of the ground. See RuinsDepth.
	RuinsSprite->SetUsingAbsoluteRotation(true);
	RuinsSprite->TranslucencySortPriority = -900;
}

void APTKGuardBase::BeginPlay()
{
	Super::BeginPlay();

	if (Capsule)
	{
		Capsule->SetCapsuleSize(CollisionRadius, CollisionHalfHeight);
	}

	if (RuinsSprite)
	{
		// The crop was taken at this base's own map coordinates, so it only has
		// to be pushed back along the depth axis - never offset sideways.
		RuinsSprite->SetRelativeLocation(FVector(0.0f, RuinsDepth, 0.0f));
		if (DestroyedSprite)
		{
			RuinsSprite->SetSprite(DestroyedSprite);
		}
		RuinsSprite->SetVisibility(false);
	}

	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(MaxHealth);
		HealthComponent->OnHealthChanged.AddDynamic(this, &APTKGuardBase::HandleHealthChanged);
		HealthComponent->OnDeath.AddDynamic(this, &APTKGuardBase::HandleDestroyed);
	}

	if (APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Field->RegisterBase(this);
	}

	UE_LOG(LogPTK, Log, TEXT("BASE | %s ready | %.0f HP at %s"),
		*GuardId.ToString(), MaxHealth, *GetActorLocation().ToString());
}

void APTKGuardBase::EndPlay(const EEndPlayReason::Type Reason)
{
	if (APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Field->UnregisterBase(this);
	}
	Super::EndPlay(Reason);
}

float APTKGuardBase::GetTimeSinceDamaged() const
{
	if (LastDamagedTime < 0.0f || !GetWorld())
	{
		return TNumericLimits<float>::Max();
	}
	return GetWorld()->GetTimeSeconds() - LastDamagedTime;
}

bool APTKGuardBase::IsUnderAttack() const
{
	return !bDestroyed && GetTimeSinceDamaged() <= UnderAttackWindow;
}

void APTKGuardBase::HandleHealthChanged(UPTKHealthComponent* Component, float NewHealth,
	float Delta, AActor* DamageInstigator)
{
	if (Delta < 0.0f && GetWorld())
	{
		LastDamagedTime = GetWorld()->GetTimeSeconds();
	}
}

void APTKGuardBase::HandleDestroyed(UPTKHealthComponent* Component, AActor* Killer)
{
	if (bDestroyed)
	{
		return;
	}
	bDestroyed = true;

	// Stops accepting damage but stays in the world - the minimap still draws it
	// as ground that has been lost. See the header.
	if (HealthComponent)
	{
		HealthComponent->SetDamageImmune(true);
	}
	if (Capsule)
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	// The ruins appear and stay. The base actor is never destroyed - the
	// minimap keeps drawing it as ground that has been lost, and the world
	// keeps showing why.
	if (RuinsSprite && DestroyedSprite)
	{
		RuinsSprite->SetSprite(DestroyedSprite);
		RuinsSprite->SetVisibility(true);
	}

	if (UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld()))
	{
		Analytics->NotifyBaseDestroyed(this);
	}

	UE_LOG(LogPTK, Warning, TEXT("BASE DESTROYED | %s | enemies will reacquire%s"),
		*GuardId.ToString(),
		(RuinsSprite && DestroyedSprite) ? TEXT("") : TEXT(" (no ruins art assigned)"));
}

void APTKGuardBase::DebugApplyDamage(float Amount)
{
	if (HealthComponent)
	{
		HealthComponent->ApplyDamage(Amount, this);
	}
}
